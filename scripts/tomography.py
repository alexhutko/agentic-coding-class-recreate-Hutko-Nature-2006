"""First-order travel-time perturbation on an unperturbed reference ray.

This operator is implemented and tested, but the UT, UCB and CIT numerical
coefficients cannot be reconstructed from the permitted written descriptions.
It is NOT a replacement tomography model or a fitted image correction.
"""
import numpy as np


def perturbation(reference_segment_time_s, fractional_vs_anomaly):
    """delta T = -integral (delta Vs / Vs) dt, midpoint sampled on ray segments.

    Supply the same 3-D model evaluator on both scattering legs and on the
    reference ray. Migrate with delta T_source + delta T_receiver - delta T_ref.
    """
    dt=np.asarray(reference_segment_time_s)
    anomaly=np.asarray(fractional_vs_anomaly)
    if dt.shape!=anomaly.shape:raise ValueError('One fractional anomaly per ray segment')
    if np.any(dt<0):raise ValueError('Segment travel time must be nonnegative')
    return -float(np.sum(dt*anomaly))
