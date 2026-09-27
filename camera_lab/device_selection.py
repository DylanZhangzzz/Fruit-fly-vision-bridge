"""Select a device explicitly when more than one RealSense is connected."""
import os


def select_serial(serial=None):
    import pyrealsense2 as rs
    requested = serial or os.environ.get("FLYVISION_REALSENSE_SERIAL")
    available = [d.get_info(rs.camera_info.serial_number) for d in rs.context().query_devices()]
    if requested:
        if requested not in available:
            raise RuntimeError("Requested RealSense is not connected; check FLYVISION_REALSENSE_SERIAL.")
        return requested
    if len(available) != 1:
        raise RuntimeError("Connect exactly one RealSense, or select one with FLYVISION_REALSENSE_SERIAL.")
    return available[0]
