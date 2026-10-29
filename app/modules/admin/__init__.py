from .routes import ns


def register(api):
    api.add_namespace(ns, path="/users")
