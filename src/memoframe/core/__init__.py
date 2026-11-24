"""Core image-processing building blocks (no database access in this package).

Submodules are imported explicitly by callers so that importing ``core`` stays
cheap and does not pull in OpenCV or scikit-learn.
"""