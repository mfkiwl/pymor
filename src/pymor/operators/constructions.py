# This file is part of the pyMOR project (http://www.pymor.org).
# Copyright 2013-2020 pyMOR developers and contributors. All rights reserved.
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

"""Module containing some constructions to obtain new operators from old ones."""

from functools import reduce
from itertools import chain
from numbers import Number

import numpy as np
import scipy.linalg as spla

from pymor.core.defaults import defaults
from pymor.core.exceptions import InversionError
from pymor.operators.interface import Operator
from pymor.parameters.base import ParametricObject
from pymor.parameters.functionals import ParameterFunctional, ConjugateParameterFunctional
from pymor.vectorarrays.interface import VectorArray, VectorSpace
from pymor.vectorarrays.numpy import NumpyVectorArray, NumpyVectorSpace


class LincombOperator(Operator):
    """Linear combination of arbitrary |Operators|.

    This |Operator| represents a (possibly |Parameter| dependent)
    linear combination of a given list of |Operators|.

    Parameters
    ----------
    operators
        List of |Operators| whose linear combination is formed.
    coefficients
        A list of linear coefficients. A linear coefficient can
        either be a fixed number or a |ParameterFunctional|.
    solver_options
        The |solver_options| for the operator.
    name
        Name of the operator.
    """

    def __init__(self, operators, coefficients, solver_options=None, name=None):
        assert len(operators) > 0
        assert len(operators) == len(coefficients)
        assert all(isinstance(op, Operator) for op in operators)
        assert all(isinstance(c, (ParameterFunctional, Number)) for c in coefficients)
        assert all(op.source == operators[0].source for op in operators[1:])
        assert all(op.range == operators[0].range for op in operators[1:])
        operators = tuple(operators)
        coefficients = tuple(coefficients)

        self.__auto_init(locals())
        self.source = operators[0].source
        self.range = operators[0].range
        self.linear = all(op.linear for op in operators)

    @property
    def H(self):
        options = {'inverse': self.solver_options.get('inverse_adjoint'),
                   'inverse_adjoint': self.solver_options.get('inverse')} if self.solver_options else None
        return self.with_(operators=[op.H for op in self.operators], solver_options=options,
                          coefficients=[ConjugateParameterFunctional(c) if isinstance(c, ParameterFunctional)
                                        else np.conj(c)
                                        for c in self.coefficients],
                          name=self.name + '_adjoint')

    def evaluate_coefficients(self, mu):
        """Compute the linear coefficients for given |parameter values|.

        Parameters
        ----------
        mu
            |Parameter values| for which to compute the linear coefficients.

        Returns
        -------
        List of linear coefficients.
        """
        assert self.parameters.assert_compatible(mu)
        return [c.evaluate(mu) if hasattr(c, 'evaluate') else c for c in self.coefficients]

    def apply(self, U, mu=None):
        coeffs = self.evaluate_coefficients(mu)
        if np.linalg.norm(coeffs) == 0:
            R = NumpyVectorArray(np.ndarray((1,self.operators[0].range.dim),buffer= np.zeros(self.operators[0].range.dim)),self.operators[0].range) 
        else:
            if coeffs[0]!= 0.0:
                R = self.operators[0].apply(U, mu=mu)
                R.scal(coeffs[0])
            else:
                R = NumpyVectorArray(np.ndarray((1,self.operators[0].range.dim),buffer= np.zeros(self.operators[0].range.dim)),self.operators[0].range) 
            for op, c in zip(self.operators[1:], coeffs[1:]):
                if c!= 0.0:
                    R.axpy(c, op.apply(U, mu=mu))
        return R

    def apply2(self, V, U, mu=None):
        coeffs = self.evaluate_coefficients(mu)
        if np.linalg.norm(coeffs) == 0:
            R = np.ndarray((1,1),buffer= np.array([0.0]))  
        else:
            if coeffs[0]!= 0.0:
                coeffs_dtype = reduce(np.promote_types, (type(c) for c in coeffs))
                m = self.operators[0].apply2(V, U, mu=mu)
                R = coeffs[0]*m
                common_dtype = np.promote_types(coeffs_dtype,m.dtype)
            else:
                R = np.ndarray((1,1),buffer= np.array([0.0]))
                common_dtype = reduce(np.promote_types, (type(c) for c in coeffs))
            if R.dtype != common_dtype:
                    R = R.astype(common_dtype)
            i = 0
            for c in coeffs[1:]:
                i = i + 1
                if c!=0.0:
                    m = self.operators[i].apply2(V,U,mu=mu)
                    common_dtype = np.promote_types(common_dtype,m.dtype)
                    R += c*m
                    if R.dtype != common_dtype:
                        R = R.astype(common_dtype)
        return R

    def pairwise_apply2(self, V, U, mu=None):
        coeffs = self.evaluate_coefficients(mu)
        if np.linalg.norm(coeffs) == 0:
            R = np.ndarray((1,1),buffer= np.array([0.0]))  
        else:
            if coeffs[0]!= 0.0:
                coeffs_dtype = reduce(np.promote_types, (type(c) for c in coeffs))
                v = self.operators[0].pairwise_apply2(V, U, mu=mu)
                R = coeffs[0]*v
                common_dtype = np.promote_types(coeffs_dtype,v.dtype)
            else:
                R = np.ndarray((1,1),buffer= np.array([0.0]))  
                common_dtype = reduce(np.promote_types, (type(c) for c in coeffs))
            if R.dtype!= common_dtype:
                R = R.astype(common_dtype)
            i = 0
            for c in coeffs[1:]:
                i = i+1
                if c!= 0.0:
                    v = self.operators[i].pairwise_apply2(V, U, mu= mu)
                    common_dtype = np.promote_types(common_dtype,v.dtype)
                    R += c * v
                    if R.dtype!= common_dtype:
                        R = R.astype(common_dtype)
        return R

    def apply_adjoint(self, V, mu=None):
        coeffs = self.evaluate_coefficients(mu)
        if np.linalg.norm(coeffs) == 0:
            R = NumpyVectorArray(np.ndarray((1,self.operators[0].source.dim),buffer= np.zeros(self.operators[0].source.dim)),self.operators[0].source) 
        else:
            if coeffs[0]!= 0.0:
                R = self.operators[0].apply_adjoint(V, mu=mu)
                R.scal(np.conj(coeffs[0]))
            else:
                R= NumpyVectorArray(np.ndarray((1,self.operators[0].source.dim),buffer= np.zeros(self.operators[0].source.dim)),self.operators[0].source) 
            for op, c in zip(self.operators[1:], coeffs[1:]):
                if c!= 0.0:
                    R.axpy(np.conj(c), op.apply_adjoint(V, mu=mu))
        return R

    def assemble(self, mu=None):
        from pymor.algorithms.lincomb import assemble_lincomb
        operators = tuple(op.assemble(mu) for op in self.operators)
        coefficients = self.evaluate_coefficients(mu)
        op = assemble_lincomb(operators, coefficients, solver_options=self.solver_options,
                              name=self.name + '_assembled')
        if op:
            return op
        else:
            if self.parametric or operators != self.operators:
                return LincombOperator(operators, coefficients, solver_options=self.solver_options,
                                       name=self.name + '_assembled')
            else:  # this can only happen when both operators and self.operators are tuples!
                return self  # avoid infinite recursion

    def jacobian(self, U, mu=None):
        from pymor.algorithms.lincomb import assemble_lincomb
        if self.linear:
            return self.assemble(mu)
        jacobians = [op.jacobian(U, mu) for op in self.operators]
        coefficients = self.evaluate_coefficients(mu)
        options = self.solver_options.get('jacobian') if self.solver_options else None
        jac = assemble_lincomb(jacobians, coefficients, solver_options=options,
                               name=self.name + '_jacobian')
        if jac is None:
            return LincombOperator(jacobians, coefficients, solver_options=options,
                                   name=self.name + '_jacobian')
        else:
            return jac

    def d_mu(self, parameter, index=0):
        for op in self.operators:
            if parameter in op.parameters:
                raise NotImplementedError
        derivative_coefficients = []
        for coef in self.coefficients:
            if isinstance(coef, ParametricObject):
                derivative_coefficients.append(coef.d_mu(parameter, index))
            else:
                derivative_coefficients.append(0.)
        return self.with_(coefficients=derivative_coefficients, name=self.name + '_d_mu')

    def apply_inverse(self, V, mu=None, least_squares=False):
        if len(self.operators) == 1:
            if self.coefficients[0] == 0.:
                if least_squares:
                    return self.source.zeros(len(V))
                else:
                    raise InversionError
            else:
                U = self.operators[0].apply_inverse(V, mu=mu, least_squares=least_squares)
                U *= (1. / self.coefficients[0])
                return U
        else:
            return super().apply_inverse(V, mu=mu, least_squares=least_squares)

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        if len(self.operators) == 1:
            if self.coefficients[0] == 0.:
                if least_squares:
                    return self.range.zeros(len(U))
                else:
                    raise InversionError
            else:
                V = self.operators[0].apply_inverse_adjoint(U, mu=mu, least_squares=least_squares)
                V *= (1. / self.coefficients[0])
                return V
        else:
            return super().apply_inverse_adjoint(U, mu=mu, least_squares=least_squares)

    def _as_array(self, source, mu):
        coefficients = np.array(self.evaluate_coefficients(mu))
        arrays = [op.as_source_array(mu) if source else op.as_range_array(mu) for op in self.operators]
        R = arrays[0]
        R.scal(coefficients[0])
        for c, v in zip(coefficients[1:], arrays[1:]):
            R.axpy(c, v)
        return R

    def as_range_array(self, mu=None):
        return self._as_array(False, mu)

    def as_source_array(self, mu=None):
        return self._as_array(True, mu)

    def _add_sub(self, other, sign):
        if not isinstance(other, Operator):
            return NotImplemented

        if self.name != 'LincombOperator':
            if isinstance(other, LincombOperator) and other.name == 'LincombOperator':
                operators = (self,) + other.operators
                coefficients = (1.,) + (other.coefficients if sign == 1. else tuple(-c for c in other.coefficients))
            else:
                operators, coefficients = (self, other), (1., sign)
        elif isinstance(other, LincombOperator) and other.name == 'LincombOperator':
            operators = self.operators + other.operators
            coefficients = self.coefficients + (other.coefficients if sign == 1.
                                                else tuple(-c for c in other.coefficients))
        else:
            operators, coefficients = self.operators + (other,), self.coefficients + (sign,)

        return LincombOperator(operators, coefficients, solver_options=self.solver_options)

    def _radd_sub(self, other, sign):
        if not isinstance(other, Operator):
            return NotImplemented

        # note that 'other' can never be a LincombOperator
        if self.name != 'LincombOperator':
            operators, coefficients = (other, self), (1., sign)
        else:
            operators = (other,) + self.operators
            coefficients = (1.,) + (self.coefficients if sign == 1. else tuple(-c for c in self.coefficients))

        return LincombOperator(operators, coefficients, solver_options=other.solver_options)

    def __add__(self, other):
        return self._add_sub(other, 1.)

    def __sub__(self, other):
        return self._add_sub(other, -1.)

    def __radd__(self, other):
        return self._radd_sub(other, 1.)

    def __rsub__(self, other):
        return self._radd_sub(other, -1.)

    def __mul__(self, other):
        assert isinstance(other, (Number, ParameterFunctional))
        if self.name != 'LincombOperator':
            return LincombOperator((self,), (other,))
        else:
            return self.with_(coefficients=tuple(c * other for c in self.coefficients))


class Concatenation(Operator):
    """|Operator| representing the concatenation of two |Operators|.

    Parameters
    ----------
    operators
        Tuple  of |Operators| to concatenate. `operators[-1]`
        is the first applied operator, `operators[0]` is the last
        applied operator.
    solver_options
        The |solver_options| for the operator.
    name
        Name of the operator.
    """

    def __init__(self, operators, solver_options=None, name=None):
        assert all(isinstance(op, Operator) for op in operators)
        assert all(operators[i].source == operators[i+1].range for i in range(len(operators)-1))
        operators = tuple(operators)

        self.__auto_init(locals())
        self.source = operators[-1].source
        self.range = operators[0].range
        self.linear = all(op.linear for op in operators)

    @property
    def H(self):
        options = {'inverse': self.solver_options.get('inverse_adjoint'),
                   'inverse_adjoint': self.solver_options.get('inverse')} if self.solver_options else None
        return type(self)(tuple(op.H for op in self.operators[::-1]), solver_options=options,
                          name=self.name + '_adjoint')

    def apply(self, U, mu=None):
        assert self.parameters.assert_compatible(mu)
        for op in self.operators[::-1]:
            U = op.apply(U, mu=mu)
        return U

    def apply_adjoint(self, V, mu=None):
        assert self.parameters.assert_compatible(mu)
        for op in self.operators:
            V = op.apply_adjoint(V, mu=mu)
        return V

    def jacobian(self, U, mu=None):
        assert len(U) == 1
        Us = [U]
        for op in self.operators[:0:-1]:
            Us.append(op.apply(Us[-1], mu=mu))
        options = self.solver_options.get('jacobian') if self.solver_options else None
        return Concatenation(tuple(op.jacobian(U, mu=mu) for op, U in zip(self.operators, Us[::-1])),
                             solver_options=options, name=self.name + '_jacobian')

    def restricted(self, dofs):
        restricted_ops = []
        for op in self.operators:
            rop, dofs = op.restricted(dofs)
            restricted_ops.append(rop)
        return Concatenation(restricted_ops), dofs

    def __matmul__(self, other):
        if not isinstance(other, Operator):
            return NotImplemented

        if self.name != 'Concatenation':
            if isinstance(other, Concatenation) and other.name == 'Concatenation':
                operators = (self,) + other.operators
            else:
                operators = (self, other)
        elif isinstance(other, Concatenation) and other.name == 'Concatenation':
            operators = self.operators + other.operators
        else:
            operators = self.operators + (other,)

        return Concatenation(operators, solver_options=self.solver_options)

    def __rmatmul__(self, other):
        if not isinstance(other, Operator):
            return NotImplemented

        # note that 'other' can never be a Concatenation
        if self.name != 'Concatenation':
            operators = (other, self)
        else:
            operators = (other,) + self.operators

        return Concatenation(operators, solver_options=other.solver_options)


class ProjectedOperator(Operator):
    """Generic |Operator| representing the projection of an |Operator| to a subspace.

    This operator is implemented as the concatenation of the linear combination with
    `source_basis`, application of the original `operator` and projection onto
    `range_basis`. As such, this operator can be used to obtain a reduced basis
    projection of any given |Operator|. However, no offline/online decomposition is
    performed, so this operator is mainly useful for testing before implementing
    offline/online decomposition for a specific application.

    This operator is instantiated in :func:`pymor.algorithms.projection.project`
    as a default implementation for parametric or nonlinear operators.

    Parameters
    ----------
    operator
        The |Operator| to project.
    range_basis
        See :func:`pymor.algorithms.projection.project`.
    source_basis
        See :func:`pymor.algorithms.projection.project`.
    product
        See :func:`pymor.algorithms.projection.project`.
    solver_options
        The |solver_options| for the projected operator.
    """

    linear = False

    def __init__(self, operator, range_basis, source_basis, product=None, solver_options=None):
        assert isinstance(operator, Operator)
        assert source_basis is None or source_basis in operator.source
        assert range_basis is None or range_basis in operator.range
        assert (product is None
                or (isinstance(product, Operator)
                    and range_basis is not None
                    and operator.range == product.source
                    and product.range == product.source))
        if source_basis is not None:
            source_basis = source_basis.copy()
        if range_basis is not None:
            range_basis = range_basis.copy()
        self.__auto_init(locals())
        self.source = NumpyVectorSpace(len(source_basis)) if source_basis is not None else operator.source
        self.range = NumpyVectorSpace(len(range_basis)) if range_basis is not None else operator.range
        self.linear = operator.linear

    @property
    def H(self):
        if self.product:
            return super().H
        else:
            options = {'inverse': self.solver_options.get('inverse_adjoint'),
                       'inverse_adjoint': self.solver_options.get('inverse')} if self.solver_options else None
            return ProjectedOperator(self.operator.H, self.source_basis, self.range_basis, solver_options=options)

    def apply(self, U, mu=None):
        assert self.parameters.assert_compatible(mu)
        if self.source_basis is None:
            if self.range_basis is None:
                return self.operator.apply(U, mu=mu)
            elif self.product is None:
                return self.range.make_array(self.operator.apply2(self.range_basis, U, mu=mu).T)
            else:
                V = self.operator.apply(U, mu=mu)
                return self.range.make_array(self.product.apply2(V, self.range_basis))
        else:
            UU = self.source_basis.lincomb(U.to_numpy())
            if self.range_basis is None:
                return self.operator.apply(UU, mu=mu)
            elif self.product is None:
                return self.range.make_array(self.operator.apply2(self.range_basis, UU, mu=mu).T)
            else:
                V = self.operator.apply(UU, mu=mu)
                return self.range.make_array(self.product.apply2(V, self.range_basis))

    def jacobian(self, U, mu=None):
        assert len(U) == 1
        assert self.parameters.assert_compatible(mu)
        if self.linear:
            return self.assemble(mu)
        if self.source_basis is None:
            J = self.operator.jacobian(U, mu=mu)
        else:
            J = self.operator.jacobian(self.source_basis.lincomb(U.to_numpy()), mu=mu)
        from pymor.algorithms.projection import project
        pop = project(J, range_basis=self.range_basis, source_basis=self.source_basis,
                      product=self.product)
        if self.solver_options:
            options = self.solver_options.get('jacobian')
            if options:
                pop = pop.with_(solver_options=options)
        return pop

    def assemble(self, mu=None):
        op = self.operator.assemble(mu=mu)
        if op == self.operator:  # avoid infinite recursion in apply_inverse default impl
            return self
        from pymor.algorithms.projection import project
        pop = project(op, range_basis=self.range_basis, source_basis=self.source_basis,
                      product=self.product)
        if self.solver_options:
            pop = pop.with_(solver_options=self.solver_options)
        return pop

    def apply_adjoint(self, V, mu=None):
        assert V in self.range
        if self.range_basis is not None:
            V = self.range_basis.lincomb(V.to_numpy())
        U = self.operator.apply_adjoint(V, mu)
        if self.source_basis is not None:
            U = self.source.make_array(U.dot(self.source_basis))
        return U


class LowRankOperator(Operator):
    """Non-parametric low-rank operator.

    Represents an operator of the form :math:`L C R^H` or
    :math:`L C^{-1} R^H` where :math:`L` and :math:`R` are
    |VectorArrays| of column vectors and :math:`C` a 2D |NumPy array|.

    Parameters
    ----------
    left
        |VectorArray| representing :math:`L`.
    core
        |NumPy array| representing :math:`C`.
    right
        |VectorArray| representing :math:`R`.
    inverted
        Whether :math:`C` is inverted.
    solver_options
        The |solver_options| for the operator.
    name
        Name of the operator.
    """

    linear = True

    def __init__(self, left, core, right, inverted=False, solver_options=None, name=None):
        assert isinstance(left, VectorArray)
        assert isinstance(right, VectorArray)
        assert len(left) == len(right)
        assert (isinstance(core, np.ndarray)
                and core.ndim == 2
                and core.shape[0] == core.shape[1] == len(left))

        self.__auto_init(locals())
        self.source = right.space
        self.range = left.space

    @property
    def H(self):
        options = {
            'inverse': self.solver_options.get('inverse_adjoint'),
            'inverse_adjoint': self.solver_options.get('inverse'),
        } if self.solver_options else None
        return type(self)(self.right,
                          self.core.T.conj(),
                          self.left,
                          inverted=self.inverted,
                          solver_options=options,
                          name=self.name + '_adjoint')

    def apply(self, U, mu=None):
        assert U in self.source
        V = self.right.dot(U)
        if self.inverted:
            V = spla.solve(self.core, V)
        else:
            V = self.core @ V
        return self.left.lincomb(V.T)

    def apply_adjoint(self, V, mu=None):
        assert V in self.range
        U = self.left.dot(V)
        if self.inverted:
            U = spla.solve(self.core.T.conj(), U)
        else:
            U = self.core.T.conj() @ U
        return self.right.lincomb(U.T)


class LowRankUpdatedOperator(LincombOperator):
    r"""|Operator| plus :class:`LowRankOperator`.

    Represents a linear combination of an |Operator| and
    :class:`LowRankOperator`. Uses the Sherman-Morrison-Woodbury formula
    in `apply_inverse` and `apply_inverse_adjoint`:

    .. math::
        \left(\alpha A + \beta L C R^H \right)^{-1}
        & = \alpha^{-1} A^{-1}
            - \alpha^{-1} \beta A^{-1} L C
            \left(\alpha C + \beta C R^H A^{-1} L C \right)^{-1}
            C R^H A^{-1}, \\
        \left(\alpha A + \beta L C^{-1} R^H \right)^{-1}
        & = \alpha^{-1} A^{-1}
            - \alpha^{-1} \beta A^{-1} L
            \left(\alpha C + \beta R^H A^{-1} L \right)^{-1}
            R^H A^{-1}.

    Parameters
    ----------
    operator
        |Operator|.
    lr_operator
        :class:`LowRankOperator`.
    coeff
        A linear coefficient for `operator`. Can either be a fixed
        number or a |ParameterFunctional|.
    lr_coeff
        A linear coefficient for `lr_operator`. Can either be a fixed
        number or a |ParameterFunctional|.
    solver_options
        The |solver_options| for the operator.
    name
        Name of the operator.
    """

    def __init__(self, operator, lr_operator, coeff, lr_coeff,
                 solver_options=None, name=None):
        assert isinstance(lr_operator, LowRankOperator)
        super().__init__([operator, lr_operator], [coeff, lr_coeff],
                         solver_options=solver_options, name=name)
        self.__auto_init(locals())

    def apply_inverse(self, V, mu=None, least_squares=False):
        if least_squares:
            return super().apply_inverse(V, mu=mu, least_squares=True)
        A, LR = self.operators
        L, C, R = LR.left, LR.core, LR.right
        if not LR.inverted:
            L = L.lincomb(C.T)
            R = R.lincomb(C.conj())
        alpha, beta = self.evaluate_coefficients(mu)
        AinvV = A.apply_inverse(V)
        AinvL = A.apply_inverse(L)
        mat = alpha * C + beta * R.dot(AinvL)
        RhAinvV = R.dot(AinvV)
        U = AinvV
        U.axpy(-beta, AinvL.lincomb(spla.solve(mat, RhAinvV).T))
        U.scal(1 / alpha)
        return U

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        if least_squares:
            return super().apply_inverse_adjoint(U, mu=mu, least_squares=True)
        A, LR = self.operators
        L, C, R = LR.left, LR.core, LR.right
        if not LR.inverted:
            L = L.lincomb(C.T)
            R = R.lincomb(C.conj())
        alpha, beta = (c.conjugate() for c in self.evaluate_coefficients(mu))
        AinvhU = A.apply_inverse_adjoint(U)
        AinvhR = A.apply_inverse_adjoint(R)
        mat = alpha * C.T.conj() + beta * L.dot(AinvhR)
        LhAinvhU = L.dot(AinvhU)
        V = AinvhU
        V.axpy(-beta, AinvhR.lincomb(spla.solve(mat, LhAinvhU).T))
        V.scal(1 / alpha)
        return V


class ComponentProjection(Operator):
    """|Operator| representing the projection of a |VectorArray| onto some of its components.

    Parameters
    ----------
    components
        List or 1D |NumPy array| of the indices of the vector
        :meth:`~pymor.vectorarrays.interface.VectorArray.components` that are
        to be extracted by the operator.
    source
        Source |VectorSpace| of the operator.
    name
        Name of the operator.
    """

    linear = True

    def __init__(self, components, source, name=None):
        assert all(0 <= c < source.dim for c in components)
        components = np.array(components, dtype=np.int32)

        self.__auto_init(locals())
        self.range = NumpyVectorSpace(len(components))

    def apply(self, U, mu=None):
        assert U in self.source
        return self.range.make_array(U.dofs(self.components))

    def restricted(self, dofs):
        assert all(0 <= c < self.range.dim for c in dofs)
        source_dofs = self.components[dofs]
        return IdentityOperator(NumpyVectorSpace(len(source_dofs))), source_dofs


class IdentityOperator(Operator):
    """The identity |Operator|.

    In other words::

        op.apply(U) == U

    Parameters
    ----------
    space
        The |VectorSpace| the operator acts on.
    name
        Name of the operator.
    """

    linear = True

    def __init__(self, space, name=None):
        self.__auto_init(locals())
        self.source = self.range = space

    @property
    def H(self):
        return self

    def apply(self, U, mu=None):
        assert U in self.source
        return U.copy()

    def apply_adjoint(self, V, mu=None):
        assert V in self.range
        return V.copy()

    def apply_inverse(self, V, mu=None, least_squares=False):
        assert V in self.range
        return V.copy()

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        assert U in self.source
        return U.copy()

    def assemble(self, mu=None):
        return self

    def restricted(self, dofs):
        assert all(0 <= c < self.range.dim for c in dofs)
        return IdentityOperator(NumpyVectorSpace(len(dofs))), dofs


class ConstantOperator(Operator):
    """A constant |Operator| always returning the same vector.

    Parameters
    ----------
    value
        A |VectorArray| of length 1 containing the vector which is
        returned by the operator.
    source
        Source |VectorSpace| of the operator.
    name
        Name of the operator.
    """

    linear = False

    def __init__(self, value, source, name=None):
        assert isinstance(value, VectorArray)
        assert len(value) == 1
        value = value.copy()

        self.__auto_init(locals())
        self.range = value.space

    def apply(self, U, mu=None):
        assert U in self.source
        return self.value[[0] * len(U)].copy()

    def jacobian(self, U, mu=None):
        assert U in self.source
        assert len(U) == 1
        return ZeroOperator(self.range, self.source, name=self.name + '_jacobian')

    def restricted(self, dofs):
        assert all(0 <= c < self.range.dim for c in dofs)
        restricted_value = NumpyVectorSpace.make_array(self.value.dofs(dofs))
        return ConstantOperator(restricted_value, NumpyVectorSpace(len(dofs))), dofs

    def apply_inverse(self, V, mu=None, least_squares=False):
        if not least_squares:
            raise InversionError('ConstantOperator is not invertible.')
        return self.source.zeros(len(V))


class ZeroOperator(Operator):
    """The |Operator| which maps every vector to zero.

    Parameters
    ----------
    range
        Range |VectorSpace| of the operator.
    source
        Source |VectorSpace| of the operator.
    name
        Name of the operator.
    """

    linear = True

    def __init__(self, range, source, name=None):
        assert isinstance(range, VectorSpace)
        assert isinstance(source, VectorSpace)
        self.__auto_init(locals())

    @property
    def H(self):
        return type(self)(self.source, self.range, name=self.name + '_adjoint')

    def apply(self, U, mu=None):
        assert U in self.source
        return self.range.zeros(len(U))

    def apply_adjoint(self, V, mu=None):
        assert V in self.range
        return self.source.zeros(len(V))

    def apply_inverse(self, V, mu=None, least_squares=False):
        assert V in self.range
        if not least_squares:
            raise InversionError
        return self.source.zeros(len(V))

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        assert U in self.source
        if not least_squares:
            raise InversionError
        return self.range.zeros(len(U))

    def restricted(self, dofs):
        assert all(0 <= c < self.range.dim for c in dofs)
        return ZeroOperator(NumpyVectorSpace(len(dofs)), NumpyVectorSpace(0)), np.array([], dtype=np.int32)


class VectorArrayOperator(Operator):
    """Wraps a |VectorArray| as an |Operator|.

    If `adjoint` is `False`, the operator maps from `NumpyVectorSpace(len(array))`
    to `array.space` by forming linear combinations of the vectors in the array
    with given coefficient arrays.

    If `adjoint == True`, the operator maps from `array.space` to
    `NumpyVectorSpace(len(array))` by forming the inner products of the argument
    with the vectors in the given array.

    Parameters
    ----------
    array
        The |VectorArray| which is to be treated as an operator.
    adjoint
        See description above.
    space_id
        Id of the `source` (`range`) |VectorSpace| in case `adjoint` is
        `False` (`True`).
    name
        The name of the operator.
    """

    linear = True

    def __init__(self, array, adjoint=False, space_id=None, name=None):
        array = array.copy()

        self.__auto_init(locals())
        if adjoint:
            self.source = array.space
            self.range = NumpyVectorSpace(len(array), space_id)
        else:
            self.source = NumpyVectorSpace(len(array), space_id)
            self.range = array.space

    @property
    def H(self):
        return VectorArrayOperator(self.array, not self.adjoint, self.space_id, self.name + '_adjoint')

    def apply(self, U, mu=None):
        assert U in self.source
        if not self.adjoint:
            return self.array.lincomb(U.to_numpy())
        else:
            return self.range.make_array(self.array.dot(U).T)

    def apply_inverse(self, V, mu=None, least_squares=False):
        if not least_squares and len(self.array) != self.array.dim:
            raise InversionError

        from pymor.algorithms.gram_schmidt import gram_schmidt
        from numpy.linalg import lstsq

        Q, R = gram_schmidt(self.array, return_R=True, reiterate=False)
        if self.adjoint:
            v = lstsq(R.T.conj(), V.to_numpy().T)[0]
            U = Q.lincomb(v.T)
        else:
            v = Q.dot(V)
            u = lstsq(R, v)[0]
            U = self.source.make_array(u.T)

        return U

    def apply_adjoint(self, V, mu=None):
        assert V in self.range
        if not self.adjoint:
            return self.source.make_array(self.array.dot(V).T)
        else:
            return self.array.lincomb(V.to_numpy())

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        adjoint_op = VectorArrayOperator(self.array, adjoint=not self.adjoint)
        return adjoint_op.apply_inverse(U, mu=mu, least_squares=least_squares)

    def as_range_array(self, mu=None):
        if not self.adjoint:
            return self.array.copy()
        else:
            return super().as_range_array(mu)

    def as_source_array(self, mu=None):
        if self.adjoint:
            return self.array.copy()
        else:
            return super().as_source_array(mu)

    def restricted(self, dofs):
        assert all(0 <= c < self.range.dim for c in dofs)
        if not self.adjoint:
            restricted_value = NumpyVectorSpace.make_array(self.array.dofs(dofs))
            return VectorArrayOperator(restricted_value, False), np.arange(self.source.dim, dtype=np.int32)
        else:
            raise NotImplementedError


class VectorOperator(VectorArrayOperator):
    """Wrap a vector as a vector-like |Operator|.

    Given a vector `v` of dimension `d`, this class represents
    the operator ::

        op: R^1 ----> R^d
             x  |---> x⋅v

    In particular::

        VectorOperator(vector).as_range_array() == vector

    Parameters
    ----------
    vector
        |VectorArray| of length 1 containing the vector `v`.
    name
        Name of the operator.
    """

    linear = True
    source = NumpyVectorSpace(1)

    def __init__(self, vector, name=None):
        assert isinstance(vector, VectorArray)
        assert len(vector) == 1
        super().__init__(vector, adjoint=False, name=name)
        self.vector = self.array  # do not init with vector arg, as vector gets copied in VectorArrayOperator.__init__


class VectorFunctional(VectorArrayOperator):
    """Wrap a vector as a linear |Functional|.

    Given a vector `v` of dimension `d`, this class represents
    the functional ::

        f: R^d ----> R^1
            u  |---> (u, v)

    where `( , )` denotes the inner product given by `product`.

    In particular, if `product` is `None` ::

        VectorFunctional(vector).as_source_array() == vector.

    If `product` is not none, we obtain ::

        VectorFunctional(vector).as_source_array() == product.apply(vector).

    Parameters
    ----------
    vector
        |VectorArray| of length 1 containing the vector `v`.
    product
        |Operator| representing the scalar product to use.
    name
        Name of the operator.
    """

    linear = True
    range = NumpyVectorSpace(1)

    def __init__(self, vector, product=None, name=None):
        assert isinstance(vector, VectorArray)
        assert len(vector) == 1
        assert product is None or isinstance(product, Operator) and vector in product.source
        if product is None:
            super().__init__(vector, adjoint=True, name=name)
        else:
            super().__init__(product.apply(vector), adjoint=True, name=name)
        self.vector = self.array  # do not init with vector arg, as vector gets copied in VectorArrayOperator.__init__
        self.product = product


class ProxyOperator(Operator):
    """Forwards all interface calls to given |Operator|.

    Mainly useful as base class for other |Operator| implementations.

    Parameters
    ----------
    operator
        The |Operator| to wrap.
    name
        Name of the wrapping operator.
    """

    def __init__(self, operator, name=None):
        assert isinstance(operator, Operator)
        self.__auto_init(locals())
        self.source = operator.source
        self.range = operator.range
        self.linear = operator.linear

    @property
    def H(self):
        return self.with_(operator=self.operator.H, name=self.name + '_adjoint')

    def apply(self, U, mu=None):
        return self.operator.apply(U, mu=mu)

    def apply_adjoint(self, V, mu=None):
        return self.operator.apply_adjoint(V, mu=mu)

    def apply_inverse(self, V, mu=None, least_squares=False):
        return self.operator.apply_inverse(V, mu=mu, least_squares=least_squares)

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        return self.operator.apply_inverse_adjoint(U, mu=mu, least_squares=least_squares)

    def jacobian(self, U, mu=None):
        return self.operator.jacobian(U, mu=mu)

    def restricted(self, dofs):
        op, source_dofs = self.operator.restricted(dofs)
        return self.with_(operator=op), source_dofs


class FixedParameterOperator(ProxyOperator):
    """Makes an |Operator| |Parameter|-independent by setting fixed |parameter values|.

    Parameters
    ----------
    operator
        The |Operator| to wrap.
    mu
        The fixed |parameter values| that will be fed to the
        :meth:`~pymor.operators.interface.Operator.apply` method
        (and related methods) of `operator`.
    """

    def __init__(self, operator, mu=None, name=None):
        super().__init__(operator, name)
        assert operator.parameters.assert_compatible(mu)
        self.mu = mu
        if mu:
            self.parameters_internal = mu.parameters

    def apply(self, U, mu=None):
        return self.operator.apply(U, mu=self.mu)

    def apply_adjoint(self, V, mu=None):
        return self.operator.apply_adjoint(V, mu=self.mu)

    def apply_inverse(self, V, mu=None, least_squares=False):
        return self.operator.apply_inverse(V, mu=self.mu, least_squares=least_squares)

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        return self.operator.apply_inverse_adjoint(U, mu=self.mu, least_squares=least_squares)

    def jacobian(self, U, mu=None):
        return self.operator.jacobian(U, mu=self.mu)


class LinearOperator(ProxyOperator):
    """Mark the wrapped |Operator| to be linear."""

    def __init__(self, operator, name=None):
        super().__init__(operator, name)
        self.linear = True


class AffineOperator(ProxyOperator):
    """Decompose an affine |Operator| into affine_shift and linear_part. """

    def __init__(self, operator, name=None):
        if operator.parametric:
            raise NotImplementedError
        super().__init__(operator, name)
        self.affine_shift = ConstantOperator(operator.apply(operator.source.zeros()), source=operator.source)
        self.linear_part = LinearOperator(operator - self.affine_shift, name=operator.name + '_linear_part')

    def jacobian(self, U, mu=None):
        return self.linear_part.jacobian(U, mu)


class InverseOperator(Operator):
    """Represents the inverse of a given |Operator|.

    Parameters
    ----------
    operator
        The |Operator| of which the inverse is formed.
    name
        If not `None`, name of the operator.
    """

    def __init__(self, operator, name=None):
        assert isinstance(operator, Operator)
        name or operator.name + '_inverse'

        self.__auto_init(locals())
        self.source = operator.range
        self.range = operator.source
        self.linear = operator.linear

    @property
    def H(self):
        return InverseAdjointOperator(self.operator)

    def apply(self, U, mu=None):
        assert U in self.source
        return self.operator.apply_inverse(U, mu=mu)

    def apply_adjoint(self, V, mu=None):
        assert V in self.range
        return self.operator.apply_inverse_adjoint(V, mu=mu)

    def apply_inverse(self, V, mu=None, least_squares=False):
        assert V in self.range
        return self.operator.apply(V, mu=mu)

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        assert U in self.source
        return self.operator.apply_adjoint(U, mu=mu)


class InverseAdjointOperator(Operator):
    """Represents the inverse adjoint of a given |Operator|.

    Parameters
    ----------
    operator
        The |Operator| of which the inverse adjoint is formed.
    name
        If not `None`, name of the operator.
    """

    linear = True

    def __init__(self, operator, name=None):
        assert isinstance(operator, Operator)
        assert operator.linear
        name = name or operator.name + '_inverse_adjoint'

        self.__auto_init(locals())
        self.source = operator.source
        self.range = operator.range

    @property
    def H(self):
        return InverseOperator(self.operator)

    def apply(self, U, mu=None):
        assert U in self.source
        return self.operator.apply_inverse_adjoint(U, mu=mu)

    def apply_adjoint(self, V, mu=None):
        assert V in self.range
        return self.operator.apply_inverse(V, mu=mu)

    def apply_inverse(self, V, mu=None, least_squares=False):
        assert V in self.range
        return self.operator.apply_adjoint(V, mu=mu)

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        assert U in self.source
        return self.operator.apply(U, mu=mu)


class AdjointOperator(Operator):
    """Represents the adjoint of a given linear |Operator|.

    For a linear |Operator| `op` the adjoint `op^*` of `op` is given by::

        (op^*(v), u)_s = (v, op(u))_r,

    where `( , )_s` and `( , )_r` denote the inner products on the source
    and range space of `op`. If two products are given by `P_s` and `P_r`, then::

        op^*(v) = P_s^(-1) o op.H o P_r,

    Thus, if `( , )_s` and `( , )_r` are the Euclidean inner products,
    `op^*v` is simply given by application of the
    :attr:adjoint <pymor.operators.interface.Operator.H>`
    |Operator|.

    Parameters
    ----------
    operator
        The |Operator| of which the adjoint is formed.
    source_product
        If not `None`, inner product |Operator| for the source |VectorSpace|
        w.r.t. which to take the adjoint.
    range_product
        If not `None`, inner product |Operator| for the range |VectorSpace|
        w.r.t. which to take the adjoint.
    name
        If not `None`, name of the operator.
    with_apply_inverse
        If `True`, provide own :meth:`~pymor.operators.interface.Operator.apply_inverse`
        and :meth:`~pymor.operators.interface.Operator.apply_inverse_adjoint`
        implementations by calling these methods on the given `operator`.
        (Is set to `False` in the default implementation of
        and :meth:`~pymor.operators.interface.Operator.apply_inverse_adjoint`.)
    solver_options
        When `with_apply_inverse` is `False`, the |solver_options| to use for
        the `apply_inverse` default implementation.
    """

    linear = True

    def __init__(self, operator, source_product=None, range_product=None, name=None,
                 with_apply_inverse=True, solver_options=None):
        assert isinstance(operator, Operator)
        assert operator.linear
        assert not with_apply_inverse or solver_options is None
        name or operator.name + '_adjoint'

        self.__auto_init(locals())
        self.source = operator.range
        self.range = operator.source

    @property
    def H(self):
        if not self.source_product and not self.range_product:
            return self.operator
        else:
            options = {'inverse': self.solver_options.get('inverse_adjoint'),
                       'inverse_adjoint': self.solver_options.get('inverse')} if self.solver_options else None
            return AdjointOperator(self.operator.H, source_product=self.range_product,
                                   range_product=self.source_product, solver_options=options)

    def apply(self, U, mu=None):
        assert U in self.source
        if self.range_product:
            U = self.range_product.apply(U)
        V = self.operator.apply_adjoint(U, mu=mu)
        if self.source_product:
            V = self.source_product.apply_inverse(V)
        return V

    def apply_adjoint(self, V, mu=None):
        assert V in self.range
        if self.source_product:
            V = self.source_product.apply_inverse(V)
        U = self.operator.apply(V, mu=mu)
        if self.range_product:
            U = self.range_product.apply(U)
        return U

    def apply_inverse(self, V, mu=None, least_squares=False):
        if not self.with_apply_inverse:
            return super().apply_inverse(V, mu=mu, least_squares=least_squares)

        assert V in self.range
        if self.source_product:
            V = self.source_product(V)
        U = self.operator.apply_inverse_adjoint(V, mu=mu, least_squares=least_squares)
        if self.range_product:
            U = self.range_product.apply_inverse(U)
        return U

    def apply_inverse_adjoint(self, U, mu=None, least_squares=False):
        if not self.with_apply_inverse:
            return super().apply_inverse_adjoint(U, mu=mu, least_squares=least_squares)

        assert U in self.source
        if self.range_product:
            U = self.range_product.apply_inverse(U)
        V = self.operator.apply_inverse(U, mu=mu, least_squares=least_squares)
        if self.source_product:
            V = self.source_product.apply(V)
        return V


class SelectionOperator(Operator):
    """An |Operator| selected from a list of |Operators|.

    `operators[i]` is used if `parameter_functional(mu)` is less or
    equal than `boundaries[i]` and greater than `boundaries[i-1]`::

        -infty ------- boundaries[i] ---------- boundaries[i+1] ------- infty
                            |                        |
        --- operators[i] ---|---- operators[i+1] ----|---- operators[i+2]
                            |                        |

    Parameters
    ----------
    operators
        List of |Operators| from which one |Operator| is
        selected based on the given |parameter values|.
    parameter_functional
        The |ParameterFunctional| used for the selection of one |Operator|.
    boundaries
        The interval boundaries as defined above.
    name
        Name of the operator.

    """
    def __init__(self, operators, parameter_functional, boundaries, name=None):
        assert len(operators) > 0
        assert len(boundaries) == len(operators) - 1
        # check that boundaries are ascending:
        for i in range(len(boundaries)-1):
            assert boundaries[i] <= boundaries[i+1]
        assert all(isinstance(op, Operator) for op in operators)
        assert all(op.source == operators[0].source for op in operators[1:])
        assert all(op.range == operators[0].range for op in operators[1:])
        operators = tuple(operators)
        boundaries = tuple(boundaries)

        self.__auto_init(locals())
        self.source = operators[0].source
        self.range = operators[0].range
        self.linear = all(op.linear for op in operators)

    @property
    def H(self):
        return self.with_(operators=[op.H for op in self.operators],
                          name=self.name + '_adjoint')

    def _get_operator_number(self, mu):
        value = self.parameter_functional.evaluate(mu)
        for i in range(len(self.boundaries)):
            if self.boundaries[i] >= value:
                return i
        return len(self.boundaries)

    def assemble(self, mu=None):
        assert self.parameters.assert_compatible(mu)
        op = self.operators[self._get_operator_number(mu)]
        return op.assemble(mu)

    def apply(self, U, mu=None):
        assert self.parameters.assert_compatible(mu)
        operator_number = self._get_operator_number(mu)
        return self.operators[operator_number].apply(U, mu=mu)

    def apply_adjoint(self, V, mu=None):
        assert self.parameters.assert_compatible(mu)
        op = self.operators[self._get_operator_number(mu)]
        return op.apply_adjoint(V, mu=mu)

    def as_range_array(self, mu=None):
        assert self.parameters.assert_compatible(mu)
        operator_number = self._get_operator_number(mu)
        return self.operators[operator_number].as_range_array(mu=mu)

    def as_source_array(self, mu=None):
        assert self.parameters.assert_compatible(mu)
        operator_number = self._get_operator_number(mu)
        return self.operators[operator_number].as_source_array(mu=mu)


@defaults('raise_negative', 'tol')
def induced_norm(product, raise_negative=True, tol=1e-10, name=None):
    """Obtain induced norm of an inner product.

    The norm of the vectors in a |VectorArray| U is calculated by
    calling ::

        product.pairwise_apply2(U, U, mu=mu).

    In addition, negative norm squares of absolute value smaller
    than `tol` are clipped to `0`.
    If `raise_negative` is `True`, a :exc:`ValueError` exception
    is raised if there are negative norm squares of absolute value
    larger than `tol`.

    Parameters
    ----------
    product
        The inner product |Operator| for which the norm is to be
        calculated.
    raise_negative
        If `True`, raise an exception if calculated norm is negative.
    tol
        See above.
    name
        optional, if None product's name is used

    Returns
    -------
    norm
        A function `norm(U, mu=None)` taking a |VectorArray| `U`
        as input together with the |parameter values| `mu` which
        are passed to the product.
    """
    return InducedNorm(product, raise_negative, tol, name)


class InducedNorm(ParametricObject):
    """Instantiated by :func:`induced_norm`. Do not use directly."""

    def __init__(self, product, raise_negative, tol, name):
        name = name or product.name
        self.__auto_init(locals())

    def __call__(self, U, mu=None):
        norm_squared = self.product.pairwise_apply2(U, U, mu=mu).real
        if self.tol > 0:
            norm_squared = np.where(np.logical_and(0 > norm_squared, norm_squared > - self.tol),
                                    0, norm_squared)
        if self.raise_negative and np.any(norm_squared < 0):
            raise ValueError(f'norm is negative (square = {norm_squared})')
        return np.sqrt(norm_squared)
