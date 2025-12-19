# Namespace package marker for Lambda layer
# This allows lambdas package to span across function package and layers
__path__ = __import__("pkgutil").extend_path(__path__, __name__)
