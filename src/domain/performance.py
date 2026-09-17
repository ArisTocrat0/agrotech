"""Motion budget from measured latency; no assumptions about camera geometry."""
import math


def motion_budget(latency_seconds, speed_kmh=20, camera_to_nozzle_m=None, actuator_ms=0):
    for name, value in [('latency_seconds', latency_seconds), ('speed_kmh', speed_kmh),
                        ('actuator_ms', actuator_ms)]:
        if not math.isfinite(value) or value < 0:
            raise ValueError(f'{name} must be finite and nonnegative')
    speed = speed_kmh / 3.6
    total = latency_seconds + actuator_ms / 1000
    result = {'speed_kmh': speed_kmh, 'latency_seconds': latency_seconds,
              'processing_distance_m': speed * latency_seconds,
              'total_distance_m': speed * total, 'camera_to_nozzle_m': camera_to_nozzle_m,
              'actuator_ms': actuator_ms, 'deadline_seconds': None,
              'within_budget': None}
    if camera_to_nozzle_m is not None:
        if not math.isfinite(camera_to_nozzle_m) or camera_to_nozzle_m <= 0 or speed <= 0:
            raise ValueError('Nozzle distance and speed must be positive')
        deadline = camera_to_nozzle_m / speed - actuator_ms / 1000
        result.update(deadline_seconds=deadline, within_budget=latency_seconds <= deadline)
    return result
