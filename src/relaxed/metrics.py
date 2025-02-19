from __future__ import annotations

__all__ = ("asimov_sig", "gaussianity")

from functools import partial
from typing import TYPE_CHECKING, cast

import jax
import jax.numpy as jnp
import jax.scipy as jsp
from jax.random import PRNGKey, multivariate_normal

from relaxed._types import Array
from relaxed.ops import fisher_info

if TYPE_CHECKING:
    import pyhf


@jax.jit
def asimov_sig(s: Array, b: Array) -> float:
    """Median expected significance for a counting experiment, valid in the asymptotic regime.
    Also valid for the multi-bin case.

    Parameters
    ----------
    s : Array
        Signal counts.
    b : Array
        Background counts.

    Returns
    -------
    float
        The expected significance.
    """
    q0 = 2 * jnp.sum((s + b) * (jnp.log(1 + s / b)) - s)
    return cast(float, q0**0.5)


def _gaussian_logpdf(
    bestfit_pars: Array,
    data: Array,
    cov: Array,
) -> Array:
    return jsp.stats.multivariate_normal.logpdf(data, bestfit_pars, cov).reshape(
        1,
    )


@partial(jax.jit, static_argnames=["model", "n_samples"])
def gaussianity(
    model: pyhf.Model,
    bestfit_pars: Array,
    data: Array,
    rng_key: PRNGKey,
    n_samples: int = 1000,
) -> Array:
    # - compare the likelihood of the fitted model with a gaussian approximation
    # that has the same MLE (fitted_pars)
    # - do this across a number of points in parspace (sampled from the gaussian approx)
    # and take the mean squared diff
    # - centre the values wrt the best-fit vals to scale the differences

    cov_approx = jnp.linalg.inv(fisher_info(model, bestfit_pars, data))

    gaussian_parspace_samples = multivariate_normal(
        key=rng_key,
        mean=bestfit_pars,
        cov=cov_approx,
        shape=(n_samples,),
    )

    relative_nlls_model = jax.vmap(
        lambda pars, data: -(
            model.logpdf(pars, data)[0] - model.logpdf(bestfit_pars, data)[0]
        ),  # scale origin to bestfit pars
        in_axes=(0, None),
    )(gaussian_parspace_samples, data)

    relative_nlls_gaussian = jax.vmap(
        lambda pars, data: -(
            _gaussian_logpdf(pars, data, cov_approx)[0]
            - _gaussian_logpdf(bestfit_pars, data, cov_approx)[0]
        ),  # data fixes the lhood shape
        in_axes=(0, None),
    )(gaussian_parspace_samples, bestfit_pars)

    diffs = relative_nlls_model - relative_nlls_gaussian
    return jnp.nanmean(diffs**2, axis=0)
