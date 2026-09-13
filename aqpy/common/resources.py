"""Process memory bounds work even when the Pi disables memory cgroups."""
import resource


def limit_address_space(mebibytes):
    if mebibytes <= 0:
        raise ValueError('Memory limit must be positive')
    requested = int(mebibytes)*1024**2
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY:
        requested = min(requested, hard)
    if soft != resource.RLIM_INFINITY:
        requested = min(requested, soft)
    resource.setrlimit(resource.RLIMIT_AS, (requested, requested))
