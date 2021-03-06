# -*- coding: utf-8 -*-
import pdb

import scipy as sp
import scipy.linalg as la
import scipy.stats as st
from limix_core.covar import FreeFormCov
from limix_core.gp import GP2KronSumLR
import random

class PredictGenEffect():
    r"""
    Predicts genetic and GxE effects for environmental states

    Parameters
    ----------
    y : (`N`, 1) ndarray
        phenotype vector
    x : (`N`, 1)
        Unstandardised SNP vector
    F : (`N`, L) ndarray
        fixed effect design for covariates.
    TrainingEnv : (`N`, `K`)
        Environmental matrix (indviduals by number of environments) on which to train the model.
    W : (`N`, `T`)
        design of random effect in the null model.
        By default, W is set to ``Env``.
    PredictEnv : (`N1`, `K`)
        Environmental matrix for which genetic predictions are to be made (number of environmental states/indviduals for which genetic effects are to be predicted by number of environments)
        By default this is generated from randomly splitting the provided ``TrainingEnv`` into two matrices of equal size to create a new ``TrainingEnv`` and ``PredictEnv``.
        To perform in-sample predictions, the same environmental matrix should be provided for both TrainingEnv and PredictEnv.
    TrainFraction : Scalar
        A value between 0 and 1 (it should not be too small or too large otherwise the predictions will not be accurate)
        If ``PredictEnv`` is None, the fraction of ``TrainingEnv`` that should be used for training and 1-``TrainingFraction`` is the fraction of ``TrainingEnv`` that should be used for prediction.



    Examples
    --------
    This example shows how to run PredictGenEffect.
    .. doctest::

        >>> from numpy.random import RandomState
        >>> import scipy as sp
        >>> from struct_lmm.interpretation import PredictGenEffect
        >>> random = RandomState(1)
        >>>
        >>> # generate data
        >>> n = 20 # number samples
        >>> k = 4 # number environments
        >>>
        >>> y = random.randn(n, 1) # phenotype
        >>> x = 1. * (random.rand(n, 1) < 0.2) # genotype
        >>> E = random.randn(n, k) # environemnts
        >>> covs = sp.ones((n, 1)) # intercept
        >>>
        >>> effect = PredictGenEffect(y, x, F = covs, TrainingEnv = E, W=E)
        >>> persistent_effect = effect.train_model()
        >>> gxe_effect = effect.predict_gxe_effect()
        >>> total_gen_effect = effect.predict_total_gen_effect()
        >>> print('%.4f' % persistent_effect, '%.4f' % gxe_effect[0], '%.4f' % total_gen_effect[0])
        ('1.3814', '0.0000', '1.3814')
    """

    def __init__(self, y, x, F, TrainingEnv, W=None, PredictEnv=None, TrainFraction = None):
        self.y = y
        self.x = x
        self.F = F
        self.TrainingEnv = TrainingEnv
        self.W = W
        self.PredictEnv = None
        self.TrainFraction = None
        if self.W is None: self.W = self.TrainingEnv
        if self.PredictEnv is None:
            if self.TrainFraction is None: self.TrainFraction = 0.5
            sp.random.seed(0)
            random_idx = sp.random.choice(sp.arange(self.TrainingEnv.shape[0]), int(self.TrainingEnv.shape[0]*self.TrainFraction), replace=False)
            self.y = self.y[random_idx]
            self.x = self.x[random_idx]
            self.F = self.F[random_idx, :]
            self.PredictEnv = self.TrainingEnv[~random_idx, :] 
            self.TrainingEnv = self.TrainingEnv[random_idx, :]
            self.W = self.W[random_idx, :]

    def train_model(self):
        _covs = sp.concatenate([self.F, self.W, self.x], 1)
        self.snp_mean = self.x.mean(0)
        self.x_std = self.x - self.snp_mean
        self.snp_std = self.x_std.std(0)
        self.x_std /= self.snp_std
        self.xoE = self.x_std*self.TrainingEnv
        gp=GP2KronSumLR(Y=self.y, F=_covs, A=sp.eye(1), Cn=FreeFormCov(1), G=self.xoE)
        gp.covar.Cr.setCovariance(1e-4 * sp.ones((1,1)))
        gp.covar.Cn.setCovariance(0.02 * sp.ones((1,1)))
        RV = gp.optimize(verbose=False)
        self.alpha = gp.b()
        self.sigma_1 = gp.covar.Cr.K()[0,0]
        self.sigma_2 = gp.covar.Cn.K()[0,0]
        self.y_adjust = self.y-sp.dot(_covs, self.alpha)
        self.persistent_effect = gp.b()[-1]

        return self.persistent_effect

    def predict_gxe_effect(self):
        ref = [0] * self.PredictEnv.shape[0]
        ref -= self.snp_mean
        ref /= self.snp_std
        alt = [1] * self.PredictEnv.shape[0]
        alt -= self.snp_mean
        alt /= self.snp_std
        x_star = sp.vstack((ref[:, sp.newaxis], alt[:, sp.newaxis]))
        E_star = sp.vstack((self.PredictEnv, self.PredictEnv))
        cent = 1/self.sigma_2*sp.dot(self.xoE.T, self.xoE)+1/self.sigma_1*sp.eye(self.TrainingEnv.shape[1])
        z_star = 1/self.sigma_2*sp.dot((x_star*E_star), sp.dot(la.inv(cent), sp.dot(self.xoE.T, self.y_adjust)))

        ref_pred = z_star[:self.PredictEnv.shape[0]]
        alt_pred = z_star[self.PredictEnv.shape[0]:]
        # effect is alt allele over and above ref allele
        self.effect = alt_pred-ref_pred

        return self.effect

    def predict_total_gen_effect(self):
        return self.persistent_effect+self.effect

