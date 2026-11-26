"""Audit UTC sampling continuity independently of a suspend-sensitive timer."""
import datetime as dt
import math

VERSION='utc-active-v1'


def audit_timing(samples,active_seconds,interval_seconds):
    issues=[];gaps=[];span=None
    if not math.isfinite(active_seconds) or active_seconds<=0:issues.append('invalid_active_elapsed')
    if not math.isfinite(interval_seconds) or interval_seconds<=0:issues.append('invalid_sampling_interval')
    try:
        times=[dt.datetime.fromisoformat(s['at']) for s in samples]
        if len(times)<2:issues.append('too_few_samples')
        else:
            gaps=[(right-left).total_seconds() for left,right in zip(times,times[1:])]
            span=(times[-1]-times[0]).total_seconds()
            if any(gap<0 for gap in gaps):issues.append('utc_clock_moved_backwards')
            if max(gaps)>max(60,3*interval_seconds):issues.append('utc_sampling_gap_above_bound')
            if abs(span-active_seconds)>max(10,2*interval_seconds):issues.append('utc_active_elapsed_disagreement')
    except (KeyError,ValueError,TypeError):issues.append('invalid_sample_timestamps')
    return {'version':VERSION,'status':'passed' if not issues else 'failed','issues':issues,
        'utc_observation_seconds':span,'active_elapsed_seconds':active_seconds,
        'max_utc_sample_gap_seconds':max(gaps,default=None),'sampling_interval_seconds':interval_seconds}
