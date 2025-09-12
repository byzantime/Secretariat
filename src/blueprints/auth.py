from quart import Blueprint
from quart import current_app
from quart import flash
from quart import g
from quart import redirect
from quart import render_template
from quart import request
from quart import url_for
from quart_auth import login_user
from quart_auth import logout_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
async def login():
    """Handle user login."""
    if g.user:
        # If user is already logged in, redirect to home
        return redirect(url_for("main.index"))

    if request.method == "POST":
        # Simple form handling without WTForms for skeleton
        form_data = await request.form
        email = form_data.get("email", "").strip()
        password = form_data.get("password", "").strip()

        if email and password:
            user_manager = current_app.extensions["user_manager"]
            user = await user_manager.authenticate_user(email, password)

            if user:
                login_user(user, remember=True)
                current_app.logger.debug(
                    f"User {user.email} authenticated successfully"
                )
                return redirect(url_for("main.index"))
            else:
                await flash("Invalid email or password.", "error")
        else:
            await flash("Email and password are required.", "error")

    return await render_template("auth/login.html")


@auth_bp.route("/logout")
async def logout():
    """Clear session and redirect to login."""
    if g.user:
        current_app.logger.debug(f"Logging out user {g.user.email}")
    logout_user()
    return redirect(url_for("auth.login"))
