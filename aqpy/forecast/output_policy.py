"""Explicit physical-domain corrections, retaining the unmodified model output."""
import math

NONNEGATIVE = {f'pm{size}_{kind}' for size in ('10','25','100') for kind in ('st','en')} | {f'p{i}' for i in range(1,7)}
POLICY_VERSION = 'physical_output_v1'


def bounds(target):
    if target in NONNEGATIVE:return 0.,None
    if target == 'humidity':return 0.,100.
    if target == 'aqi_pm':return 0.,500.
    if target == 'pressure':return 0.,None
    return None,None


def in_domain(target,value):
    if value is None or not math.isfinite(float(value)):return False
    low,high=bounds(target)
    return (low is None or value>=low) and (high is None or value<=high)


def correct_output(target,raw,baseline):
    """Return served forecast and its reason; never feed future actuals into policy.

    Negative particle outputs project to zero, the nearest physical value. Other
    domain violations use the last observed reading (persistence), avoiding an
    implausible boundary forecast such as 100% humidity. Nonfinite model outputs
    remain hard errors. Baseline must itself be a valid observed value.
    """
    raw=float(raw);baseline=float(baseline)
    if not math.isfinite(raw):raise ValueError('Nonfinite raw model forecast')
    if not in_domain(target,baseline):raise ValueError('Invalid policy baseline')
    if in_domain(target,raw):return raw,'unchanged'
    if target in NONNEGATIVE and raw<0:return 0.,'nonnegative_projection_v1'
    return baseline,'physical_persistence_v1'
