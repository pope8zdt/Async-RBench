# Compact disclosed buggy reproduction.
REF_M=1.05e-10
def sliced_world_to_pixel(lon_deg,lat_deg,slice_index=0):
    spectral_m=float(slice_index)
    return (49.5+(spectral_m-REF_M)*1e12,12.0+lat_deg/5.0)
