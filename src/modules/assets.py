"""Asset management module using Quart-Assets for cache-busting and bundling."""

from jinja_ui_kit.assets import get_css_path
from quart_assets import Bundle
from quart_assets import QuartAssets


def init_assets(app):
    """Initialize asset management with the application."""
    assets = QuartAssets(app)

    # Configure for production bundling
    app.config["ASSETS_DEBUG"] = False
    app.config["ASSETS_AUTO_BUILD"] = True

    # Register bundles
    css_bundle = Bundle(
        get_css_path(),  # jinja-ui-kit styles first
        "css/styles.css",
        "css/fontawesome.min.css",
        "css/solid.min.css",
        # filters='cssmin',  # All stylesheets already minified.
        output="css/packed-%(version)s.min.css",
    )

    js_bundle = Bundle(
        "js/htmx.min.js",
        "js/_hyperscript.min.js",
        "js/sse.min.js",
        # filters="jsmin",  # All scripts already minified.
        output="js/packed-%(version)s.min.js",
    )

    assets.register("css_all", css_bundle)
    assets.register("js_all", js_bundle)
