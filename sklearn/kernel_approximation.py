"""
The :mod:`sklearn.kernel_approximation` module implements several
approximate kernel feature maps base on Fourier transforms.
"""

# Author: Andreas Mueller <amueller@ais.uni-bonn.de>
#
# License: BSD 3 clause

import warnings

import numpy as np
from scipy.fftpack import dct
import scipy.sparse as sp
import fht as fht
from scipy.linalg import svd, hadamard
from scipy.stats import chi

from .base import BaseEstimator
from .base import TransformerMixin
from .utils import check_array, check_random_state, as_float_array
from .utils.extmath import safe_sparse_dot
from .metrics.pairwise import pairwise_kernels


class RBFSampler(BaseEstimator, TransformerMixin):
    """Approximates feature map of an RBF kernel by Monte Carlo approximation
    of its Fourier transform.

    Parameters
    ----------
    gamma : float
        Parameter of RBF kernel: exp(-gamma * x^2)

    n_components : int
        Number of Monte Carlo samples per original feature.
        Equals the dimensionality of the computed feature space.

    random_state : {int, RandomState}, optional
        If int, random_state is the seed used by the random number generator;
        if RandomState instance, random_state is the random number generator.

    Notes
    -----
    See "Random Features for Large-Scale Kernel Machines" by A. Rahimi and
    Benjamin Recht.
    """

    def __init__(self, gamma=1., n_components=100, random_state=None):
        self.gamma = gamma
        self.n_components = n_components
        self.random_state = random_state

    def fit(self, X, y=None):
        """Fit the model with X.

        Samples random projection according to n_features.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Training data, where n_samples in the number of samples
            and n_features is the number of features.

        Returns
        -------
        self : object
            Returns the transformer.
        """

        X = check_array(X, accept_sparse='csr')
        random_state = check_random_state(self.random_state)
        n_features = X.shape[1]

        self.random_weights_ = (np.sqrt(self.gamma) * random_state.normal(
            size=(n_features, self.n_components)))

        self.random_offset_ = random_state.uniform(0, 2 * np.pi,
                                                   size=self.n_components)
        return self

    def transform(self, X, y=None):
        """Apply the approximate feature map to X.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            New data, where n_samples in the number of samples
            and n_features is the number of features.

        Returns
        -------
        X_new : array-like, shape (n_samples, n_components)
        """
        X = check_array(X, accept_sparse='csr')
        projection = safe_sparse_dot(X, self.random_weights_)
        projection += self.random_offset_
        np.cos(projection, projection)
        projection *= np.sqrt(2.) / np.sqrt(self.n_components)
        return projection


class SkewedChi2Sampler(BaseEstimator, TransformerMixin):
    """Approximates feature map of the "skewed chi-squared" kernel by Monte
    Carlo approximation of its Fourier transform.

    Parameters
    ----------
    skewedness : float
        "skewedness" parameter of the kernel. Needs to be cross-validated.

    n_components : int
        number of Monte Carlo samples per original feature.
        Equals the dimensionality of the computed feature space.

    random_state : {int, RandomState}, optional
        If int, random_state is the seed used by the random number generator;
        if RandomState instance, random_state is the random number generator.

    References
    ----------
    See "Random Fourier Approximations for Skewed Multiplicative Histogram
    Kernels" by Fuxin Li, Catalin Ionescu and Cristian Sminchisescu.

    See also
    --------
    AdditiveChi2Sampler : A different approach for approximating an additive
        variant of the chi squared kernel.

    sklearn.metrics.pairwise.chi2_kernel : The exact chi squared kernel.
    """

    def __init__(self, skewedness=1., n_components=100, random_state=None):
        self.skewedness = skewedness
        self.n_components = n_components
        self.random_state = random_state

    def fit(self, X, y=None):
        """Fit the model with X.

        Samples random projection according to n_features.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Training data, where n_samples in the number of samples
            and n_features is the number of features.

        Returns
        -------
        self : object
            Returns the transformer.
        """

        X = check_array(X)
        random_state = check_random_state(self.random_state)
        n_features = X.shape[1]
        uniform = random_state.uniform(size=(n_features, self.n_components))
        # transform by inverse CDF of sech
        self.random_weights_ = (1. / np.pi
                                * np.log(np.tan(np.pi / 2. * uniform)))
        self.random_offset_ = random_state.uniform(0, 2 * np.pi,
                                                   size=self.n_components)
        return self

    def transform(self, X, y=None):
        """Apply the approximate feature map to X.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            New data, where n_samples in the number of samples
            and n_features is the number of features.

        Returns
        -------
        X_new : array-like, shape (n_samples, n_components)
        """
        X = as_float_array(X, copy=True)
        X = check_array(X, copy=False)
        if (X < 0).any():
            raise ValueError("X may not contain entries smaller than zero.")

        X += self.skewedness
        np.log(X, X)
        projection = safe_sparse_dot(X, self.random_weights_)
        projection += self.random_offset_
        np.cos(projection, projection)
        projection *= np.sqrt(2.) / np.sqrt(self.n_components)
        return projection


class AdditiveChi2Sampler(BaseEstimator, TransformerMixin):
    """Approximate feature map for additive chi2 kernel.

    Uses sampling the fourier transform of the kernel characteristic
    at regular intervals.

    Since the kernel that is to be approximated is additive, the components of
    the input vectors can be treated separately.  Each entry in the original
    space is transformed into 2*sample_steps+1 features, where sample_steps is
    a parameter of the method. Typical values of sample_steps include 1, 2 and
    3.

    Optimal choices for the sampling interval for certain data ranges can be
    computed (see the reference). The default values should be reasonable.

    Parameters
    ----------
    sample_steps : int, optional
        Gives the number of (complex) sampling points.
    sample_interval : float, optional
        Sampling interval. Must be specified when sample_steps not in {1,2,3}.

    Notes
    -----
    This estimator approximates a slightly different version of the additive
    chi squared kernel then ``metric.additive_chi2`` computes.

    See also
    --------
    SkewedChi2Sampler : A Fourier-approximation to a non-additive variant of
        the chi squared kernel.

    sklearn.metrics.pairwise.chi2_kernel : The exact chi squared kernel.

    sklearn.metrics.pairwise.additive_chi2_kernel : The exact additive chi
        squared kernel.

    References
    ----------
    See `"Efficient additive kernels via explicit feature maps"
    <http://eprints.pascal-network.org/archive/00006964/01/vedaldi10.pdf>`_
    Vedaldi, A. and Zisserman, A., Computer Vision and Pattern Recognition 2010

    """

    def __init__(self, sample_steps=2, sample_interval=None):
        self.sample_steps = sample_steps
        self.sample_interval = sample_interval

    def fit(self, X, y=None):
        """Set parameters."""
        X = check_array(X, accept_sparse='csr')
        if self.sample_interval is None:
            # See reference, figure 2 c)
            if self.sample_steps == 1:
                self.sample_interval_ = 0.8
            elif self.sample_steps == 2:
                self.sample_interval_ = 0.5
            elif self.sample_steps == 3:
                self.sample_interval_ = 0.4
            else:
                raise ValueError("If sample_steps is not in [1, 2, 3],"
                                 " you need to provide sample_interval")
        else:
            self.sample_interval_ = self.sample_interval
        return self

    def transform(self, X, y=None):
        """Apply approximate feature map to X.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape = (n_samples, n_features)

        Returns
        -------
        X_new : {array, sparse matrix}, \
               shape = (n_samples, n_features * (2*sample_steps + 1))
            Whether the return value is an array of sparse matrix depends on
            the type of the input X.
        """

        X = check_array(X, accept_sparse='csr')
        sparse = sp.issparse(X)

        # check if X has negative values. Doesn't play well with np.log.
        if ((X.data if sparse else X) < 0).any():
            raise ValueError("Entries of X must be non-negative.")
        # zeroth component
        # 1/cosh = sech
        # cosh(0) = 1.0

        transf = self._transform_sparse if sparse else self._transform_dense
        return transf(X)

    def _transform_dense(self, X):
        non_zero = (X != 0.0)
        X_nz = X[non_zero]

        X_step = np.zeros_like(X)
        X_step[non_zero] = np.sqrt(X_nz * self.sample_interval_)

        X_new = [X_step]

        log_step_nz = self.sample_interval_ * np.log(X_nz)
        step_nz = 2 * X_nz * self.sample_interval_

        for j in range(1, self.sample_steps):
            factor_nz = np.sqrt(step_nz /
                                np.cosh(np.pi * j * self.sample_interval_))

            X_step = np.zeros_like(X)
            X_step[non_zero] = factor_nz * np.cos(j * log_step_nz)
            X_new.append(X_step)

            X_step = np.zeros_like(X)
            X_step[non_zero] = factor_nz * np.sin(j * log_step_nz)
            X_new.append(X_step)

        return np.hstack(X_new)

    def _transform_sparse(self, X):
        indices = X.indices.copy()
        indptr = X.indptr.copy()

        data_step = np.sqrt(X.data * self.sample_interval_)
        X_step = sp.csr_matrix((data_step, indices, indptr),
                               shape=X.shape, dtype=X.dtype, copy=False)
        X_new = [X_step]

        log_step_nz = self.sample_interval_ * np.log(X.data)
        step_nz = 2 * X.data * self.sample_interval_

        for j in range(1, self.sample_steps):
            factor_nz = np.sqrt(step_nz /
                                np.cosh(np.pi * j * self.sample_interval_))

            data_step = factor_nz * np.cos(j * log_step_nz)
            X_step = sp.csr_matrix((data_step, indices, indptr),
                                   shape=X.shape, dtype=X.dtype, copy=False)
            X_new.append(X_step)

            data_step = factor_nz * np.sin(j * log_step_nz)
            X_step = sp.csr_matrix((data_step, indices, indptr),
                                   shape=X.shape, dtype=X.dtype, copy=False)
            X_new.append(X_step)

        return sp.hstack(X_new)


class Nystroem(BaseEstimator, TransformerMixin):
    """Approximate a kernel map using a subset of the training data.

    Constructs an approximate feature map for an arbitrary kernel
    using a subset of the data as basis.

    Parameters
    ----------
    kernel : string or callable, default="rbf"
        Kernel map to be approximated. A callable should accept two arguments
        and the keyword arguments passed to this object as kernel_params, and
        should return a floating point number.

    n_components : int
        Number of features to construct.
        How many data points will be used to construct the mapping.

    gamma : float, default=None
        Gamma parameter for the RBF, polynomial, exponential chi2 and
        sigmoid kernels. Interpretation of the default value is left to
        the kernel; see the documentation for sklearn.metrics.pairwise.
        Ignored by other kernels.

    degree : float, default=3
        Degree of the polynomial kernel. Ignored by other kernels.

    coef0 : float, default=1
        Zero coefficient for polynomial and sigmoid kernels.
        Ignored by other kernels.

    kernel_params : mapping of string to any, optional
        Additional parameters (keyword arguments) for kernel function passed
        as callable object.

    random_state : {int, RandomState}, optional
        If int, random_state is the seed used by the random number generator;
        if RandomState instance, random_state is the random number generator.


    Attributes
    ----------
    components_ : array, shape (n_components, n_features)
        Subset of training points used to construct the feature map.

    component_indices_ : array, shape (n_components)
        Indices of ``components_`` in the training set.

    normalization_ : array, shape (n_components, n_components)
        Normalization matrix needed for embedding.
        Square root of the kernel matrix on ``components_``.


    References
    ----------
    * Williams, C.K.I. and Seeger, M.
      "Using the Nystroem method to speed up kernel machines",
      Advances in neural information processing systems 2001

    * T. Yang, Y. Li, M. Mahdavi, R. Jin and Z. Zhou
      "Nystroem Method vs Random Fourier Features: A Theoretical and Empirical
      Comparison",
      Advances in Neural Information Processing Systems 2012


    See also
    --------
    RBFSampler : An approximation to the RBF kernel using random Fourier
                 features.

    sklearn.metrics.pairwise.kernel_metrics : List of built-in kernels.
    """

    def __init__(self, kernel="rbf", gamma=None, coef0=1, degree=3,
                 kernel_params=None, n_components=100, random_state=None):
        self.kernel = kernel
        self.gamma = gamma
        self.coef0 = coef0
        self.degree = degree
        self.kernel_params = kernel_params
        self.n_components = n_components
        self.random_state = random_state

    def fit(self, X, y=None):
        """Fit estimator to data.

        Samples a subset of training points, computes kernel
        on these and computes normalization matrix.

        Parameters
        ----------
        X : array-like, shape=(n_samples, n_feature)
            Training data.
        """

        rnd = check_random_state(self.random_state)
        if not sp.issparse(X):
            X = np.asarray(X)
        n_samples = X.shape[0]

        # get basis vectors
        if self.n_components > n_samples:
            # XXX should we just bail?
            n_components = n_samples
            warnings.warn("n_components > n_samples. This is not possible.\n"
                          "n_components was set to n_samples, which results"
                          " in inefficient evaluation of the full kernel.")

        else:
            n_components = self.n_components
        n_components = min(n_samples, n_components)
        inds = rnd.permutation(n_samples)
        basis_inds = inds[:n_components]
        basis = X[basis_inds]

        basis_kernel = pairwise_kernels(basis, metric=self.kernel,
                                        filter_params=True,
                                        **self._get_kernel_params())

        # sqrt of kernel matrix on basis vectors
        U, S, V = svd(basis_kernel)
        self.normalization_ = np.dot(U * 1. / np.sqrt(S), V)
        self.components_ = basis
        self.component_indices_ = inds
        return self

    def transform(self, X):
        """Apply feature map to X.

        Computes an approximate feature map using the kernel
        between some training points and X.

        Parameters
        ----------
        X : array-like, shape=(n_samples, n_features)
            Data to transform.

        Returns
        -------
        X_transformed : array, shape=(n_samples, n_components)
            Transformed data.
        """

        embedded = pairwise_kernels(X, self.components_,
                                    metric=self.kernel,
                                    filter_params=True,
                                    **self._get_kernel_params())
        return np.dot(embedded, self.normalization_.T)

    def _get_kernel_params(self):
        params = self.kernel_params
        if params is None:
            params = {}
        if not callable(self.kernel):
            params['gamma'] = self.gamma
            params['degree'] = self.degree
            params['coef0'] = self.coef0

        return params


class Fastfood(BaseEstimator, TransformerMixin):

    def __init__(self, sigma, n_components, tradeoff_less_mem_or_higher_accuracy = 'accuracy', random_state=None):
        self.sigma = sigma
        self.n_components = n_components
        self.random_state = random_state
        self.rng = check_random_state(self.random_state)
        # map to 2*n_components features or to n_components features with less accuracy
        self.tradeoff_less_mem_or_higher_accuracy = tradeoff_less_mem_or_higher_accuracy

    @staticmethod
    def is_number_power_of_two(n):
        return n != 0 and ((n & (n - 1)) == 0)

    def random_gauss_vector(self, d):
        return self.rng.normal(size=d)

    def permutation_matrix_old(self, d):
        return self.rng.permutation(np.identity(d))

    def permutation_matrix(self, d):
        p = self.rng.permutation(d)
        return p

    def binary_vector(self, d):
        return self.rng.choice([-1, 1], size=d)

    def scaling_vector_vectorized(self, d, g):
        s = np.linalg.norm(self.rng.normal(size=(d, d)), axis=0)
        return s * (1 / np.linalg.norm(g))

    # scaling_vector_iterative_time_consuming_but_lower_space_complexity
    def scaling_vector_loop(self, d, g):
        inverse_of_norm_of_G = 1 / np.linalg.norm(g)
        s = np.zeros(d)
        for i in range(d):
            length = 0
            for j in range(d):
                random_number = self.rng.randn()
                length += random_number*random_number
            s[i] = np.sqrt(length)*inverse_of_norm_of_G
        return s

    # scaling_vector_iterative_time_consuming_but_lower_space_complexity
    def scaling_vector_chi(self, d, g):
        inverse_of_norm_of_G = 1 / np.linalg.norm(g)
        return chi.rvs(d, size=d)*inverse_of_norm_of_G

    def scaling_vector(self, d, g):
        return Fastfood.scaling_vector_chi(self, d, g)

    def uniform_vector(self):
        if self.tradeoff_less_mem_or_higher_accuracy != 'accuracy':
            return self.rng.uniform(0, 2 * np.pi, size=self.n)
        else:
            return None

    def create_vectors(self):
        """ Create G, B, P and S. """
        d = self.d
        G = self.random_gauss_vector(d)
        B = self.binary_vector(d)
        P = self.permutation_matrix(d)
        S = self.scaling_vector(d, G)

        return B, G, P, S

    @staticmethod
    def enforce_dimensionality_constraints(d, n):
        if not (Fastfood.is_number_power_of_two(d)):
            # find d that fulfills 2^l
            d = np.power(2, np.floor(np.log2(d)) + 1)
        divisor, remainder = divmod(n, d)
        times_to_stack_v = int(divisor)
        if remainder != 0:
            # output info, that we increase n so that d is a divider of n
            n = (divisor + 1) * d
            times_to_stack_v = int(divisor+1)
        return int(d), int(n), times_to_stack_v

    @staticmethod
    def approx_fourier_transformation(result):
        return fht.fht1(result, normalized=False)
        #return dct(result, norm='ortho',axis=0)

    @staticmethod
    def approx_fourier_transformation_multi_dim(result):
        return fht.fht2(result, normalized=False, axes=1)
        #return dct(result, norm='ortho',axis=0)

    @staticmethod
    def hadamard(X):
        """ Abstraction for the hadamard transform.

        Doing this in a single function should eas testing different
        implementations.
        """
        # the fast hadamard transform
        return fht.fht2(X, axes=0, normalized=False)

        # the fast cosine transform, yields other mappings :-(
        # return dct(X.astype(float), norm=None)

        # full multiplication with explicit hadamard matrix
        #H = (1 / (X.shape[0] * np.sqrt(2))) * hadamard(X.shape[0])
        #H = hadamard(X.shape[0])
        # return np.dot(H, X)

    @staticmethod
    def create_gaussian_iid_matrix(b, g, p):
        """ Create HGPHB from B, G and P"""

        HB = Fastfood.hadamard(np.diag(b))
        #GP = np.dot(np.diag(G), P)
        GP = np.take(np.diag(g), p, axis=0)
        HGP = Fastfood.hadamard(GP)
        HGPHB = safe_sparse_dot(HGP, HB)
        return HGPHB

    @staticmethod
    def create_gaussian_iid_matrix_fast(b, g, p, x):
        """ Create mapping of a specific x from B, G and P"""
        result = b*x
        result = Fastfood.approx_fourier_transformation(result)
        result = np.take(result, p)
        result *= g
        result = Fastfood.approx_fourier_transformation(result)
        return result

    @staticmethod
    def create_gaussian_iid_matrix_fast_vectorized(B, G, P, X):
        """ Create mapping of a specific x from B, G and P"""
        result = np.multiply(B, X.reshape((1, X.shape[0], 1, X.shape[1])))
        result = result.reshape((X.shape[0]*B.shape[0], B.shape[1]))
        result = Fastfood.approx_fourier_transformation_multi_dim(result)
        
        Perm = np.tile(P, (X.shape[0], 1))
        np.take(result, Perm, out=result)
        result = result.reshape(X.shape[0], B.shape[0]*B.shape[1])
        np.multiply(np.ravel(G), result.reshape(X.shape[0], B.shape[0]*B.shape[1]), out=result)
        
        result = result.reshape(B.shape[0]*X.shape[0], B.shape[1])
        return Fastfood.approx_fourier_transformation_multi_dim(result)


    @staticmethod
    def create_gaussian_iid_matrix_fast_one_step(B, G, P, X):
        """ Create mapping of a specific x from B, G and P"""
        result = np.dot(np.diag(B), X)
        result = Fastfood.hadamard(result)
        result = np.take(result, P, axis=0)
        result = np.dot(np.diag(G), result)
        result = Fastfood.hadamard(result)

        return result

    def create_approximation_matrix(self, S, HGPHB):
        """ Create V from HGPHB and S """
        SHGPHB = safe_sparse_dot(np.diag(S), HGPHB)
        return 1 / (self.sigma * np.sqrt(self.d)) * SHGPHB

    def create_approximation_matrix_fast(self, S, x):
        """ Create V from HGPHB and S """
        return 1 / (self.sigma * np.sqrt(self.d)) * S*x

    def create_approximation_matrix_fast_vectorized(self, S, V):
        """ Create V from HGPHB and S """
        # S = S.reshape((1, S.shape[0]*S.shape[1])) # rival/flatten?
        V = V.reshape(-1,S.shape[0]*S.shape[1])

        return 1 / (self.sigma * np.sqrt(self.d)) * np.multiply(np.ravel(S), V)

    @staticmethod
    def phi(V, X):
        X_mapped = safe_sparse_dot(V, X.T)
        return (1 / np.sqrt(V.shape[0])) * np.vstack([np.cos(X_mapped), np.sin(X_mapped)])

    def phi_fast(self, X):
        if self.tradeoff_less_mem_or_higher_accuracy == 'accuracy':
            return (1 / np.sqrt(X.shape[1])) * np.hstack([np.cos(X), np.sin(X)])
        else:
            np.cos(X+self.U, X)
            return X * np.sqrt(2. / X.shape[1])
    
    def fit(self, X, y=None):

        d_orig = X.shape[1]

        self.d, self.n, self.times_to_stack_v = \
                Fastfood.enforce_dimensionality_constraints(d_orig, self.n_components)
        self.number_of_features_to_pad_with_zeros = self.d - d_orig

        self.vectors = [self.create_vectors()
                        for _ in range(self.times_to_stack_v)]

        self.U = self.uniform_vector()

        return self

    def fit_vectorized(self, X, y=None):

        d_orig = X.shape[1]

        self.d, self.n, self.times_to_stack_v = \
                Fastfood.enforce_dimensionality_constraints(d_orig, self.n_components)
        self.number_of_features_to_pad_with_zeros = self.d - d_orig

        self.G = self.rng.normal(size=(self.times_to_stack_v, self.d))
        self.B = self.rng.choice([-1, 1], size=(self.times_to_stack_v, self.d))
        self.P = [self.rng.permutation(self.d) for _ in range(self.times_to_stack_v)]
        self.S = np.multiply(1 / np.linalg.norm(self.G, axis=1)[:,np.newaxis],
                             chi.rvs(self.d, size=(self.times_to_stack_v, self.d)))

        self.U = self.uniform_vector()

        return self

    # def transform_fast_vectorized(self, X):
    #     X = atleast2d_or_csr(X)
    #     X_padded = self.pad_with_zeros(X)
    #     mapped_examples = []
    #     for i in range(X_padded.shape[0]):
    #         example = []
    #         HGPHBx = Fastfood.create_gaussian_iid_matrix_fast(self.B, self.G, self.P, X_padded[i, :])
    #         Vx = self.create_approximation_matrix_fast_vectorized(self.S, HGPHBx)
    #         np.reshape(Vx, (-1, 1), order='C')
    #         #print "1", type(v),v.shape
    #         mapped_examples.append(example)
    #     mapped_examples_as_matrix = np.matrix(mapped_examples)
    #     #print "4:",mapped_examples_as_matrix, mapped_examples_as_matrix.shape
    #     #print mapped_examples.count()
    #     #print mapped_examples[:5]
    #     #mapped_examples_as_matrix = np.matrix(mapped_examples, copy=True)
    #     return Fastfood.phi_fast(self, mapped_examples_as_matrix)

    def transform_fast_vectorized(self, X):
        X = atleast2d_or_csr(X)
        X_padded = self.pad_with_zeros(X)
        HGPHBX = Fastfood.create_gaussian_iid_matrix_fast_vectorized(self.B, self.G, self.P, X_padded)
        VX = self.create_approximation_matrix_fast_vectorized(self.S, HGPHBX)
        #print "4:",mapped_examples_as_matrix, mapped_examples_as_matrix.shape
        #print mapped_examples.count()
        #print mapped_examples[:5]
        #mapped_examples_as_matrix = np.matrix(mapped_examples, copy=True)
        return self.phi_fast(VX)

    def pad_with_zeros(self, X):
        X_padded = np.pad(X, ((0, 0), (0, self.number_of_features_to_pad_with_zeros)), 'constant')
        return X_padded

    def transform(self, X):

        to_stack = []
        for i in range(self.times_to_stack_v):
            B, G, P, S = self.vectors[i]
            HGPHB = Fastfood.create_gaussian_iid_matrix(B, G, P)
            v = self.create_approximation_matrix(S, HGPHB)
            to_stack.append(v)
        V_stacked = np.vstack(to_stack)

        X_padded = self.pad_with_zeros(X)
        return Fastfood.phi(V_stacked, X_padded).T

    def transform_fast(self, X):
        X = atleast2d_or_csr(X)
        X_padded = self.pad_with_zeros(X)
        mapped_examples = []
        for i in range(X_padded.shape[0]):
            example = []
            for j in range(self.times_to_stack_v):
                B, G, P, S = self.vectors[j]
                HGPHBx = Fastfood.create_gaussian_iid_matrix_fast(B, G, P, X_padded[i, :])
                v = self.create_approximation_matrix_fast(S, HGPHBx)
                #print "1", type(v),v.shape
                example.extend(v)
            mapped_examples.append(example)
        mapped_examples_as_matrix = np.matrix(mapped_examples)
        #print "4:",mapped_examples_as_matrix, mapped_examples_as_matrix.shape
        #print mapped_examples.count()
        #print mapped_examples[:5]
        #mapped_examples_as_matrix = np.matrix(mapped_examples, copy=True)
        return Fastfood.phi_fast(self, mapped_examples_as_matrix)

    def transform_fast_one_step(self, X):
        X_padded = self.pad_with_zeros(X)
        examples = []
        for j in range(self.times_to_stack_v):
            B, G, P, S = self.vectors[j]
            HGPHBx = Fastfood.create_gaussian_iid_matrix_fast_one_step(B, G, P, X_padded.T)
            v = self.create_approximation_matrix(S, HGPHBx)
            examples.append(v)
        mapped_examples_as_matrix = np.hstack(examples)

        return Fastfood.phi_fast(mapped_examples_as_matrix).T
