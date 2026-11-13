def peak_occupancy(intervals, starts_at, ends_at):
    """Máximo simultáneo; una salida libera el cupo antes de la entrada adyacente."""
    events = []
    for start, end in intervals:
        if start < ends_at and end > starts_at:
            events.extend([(max(start, starts_at), 1), (min(end, ends_at), -1)])
    occupied = peak = 0
    for _, change in sorted(events):
        occupied += change
        peak = max(peak, occupied)
    return peak
