Authentication
==============

This guide explains how authentication works in your generated project using `django-allauth <https://docs.allauth.org/>`_. It covers local accounts, social login (SSO), API authentication, and integrating with external identity providers like AWS Cognito.

Overview
--------

The template provides a complete authentication system out of the box:

- **Custom User model** configured for either email or username login (based on your ``username_type`` choice at generation)
- **Local account flows** including signup, login, logout, password reset, and email verification
- **Social authentication infrastructure** via ``allauth.socialaccount`` (providers configured separately)
- **Multi-factor authentication** via ``allauth.mfa`` with TOTP support
- **Headless/API authentication** via ``allauth.headless`` when DRF is enabled

All authentication routes are mounted at ``/accounts/`` and include ``/accounts/login/``, ``/accounts/signup/``, ``/accounts/logout/``, and ``/accounts/password/reset/``.

How Authentication Works
------------------------

The template configures two authentication backends:

1. ``django.contrib.auth.backends.ModelBackend`` — Standard Django authentication
2. ``allauth.account.auth_backends.AuthenticationBackend`` — Handles allauth flows including social login

Email verification is **mandatory in production** but **optional in development** to streamline local testing. Passwords are hashed using Argon2 (with PBKDF2 and bcrypt as fallbacks).

Template Options
^^^^^^^^^^^^^^^^

Your authentication method is determined by the ``username_type`` option at project generation:

- **username**: Users log in with a username. Email is collected but not used for login.
- **email**: Users log in with their email address. No username field exists on the User model.

This affects the ``ACCOUNT_LOGIN_METHODS`` setting (``{"username"}`` or ``{"email"}``) and cannot be easily changed after generation.

Custom Adapters
---------------

Adapters control signup and login behavior. The template includes two pre-configured adapters in ``{project_slug}/users/adapters.py``:

- **AccountAdapter**: Controls whether registration is open via ``ACCOUNT_ALLOW_REGISTRATION``
- **SocialAccountAdapter**: Same control for social signups, plus populates user data from provider info

The most common customization is restricting signups to specific email domains:

.. code-block:: python

    # {project_slug}/users/adapters.py
    class AccountAdapter(DefaultAccountAdapter):
        def is_open_for_signup(self, request: HttpRequest) -> bool:
            if not getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True):
                return False
            # Restrict to specific domains
            email = request.POST.get("email", "")
            allowed_domains = ["company.com", "partner.org"]
            domain = email.split("@")[-1] if "@" in email else ""
            return domain in allowed_domains

Single Sign-On (SSO)
--------------------

The template installs ``allauth.socialaccount`` but does not pre-configure any OAuth providers. This keeps the base template minimal while providing the infrastructure for easy SSO setup.

Adding a Social Provider
^^^^^^^^^^^^^^^^^^^^^^^^

The general pattern for adding any OAuth provider:

1. Install the provider package if needed (most are included with allauth)
2. Add the provider to ``INSTALLED_APPS``
3. Configure provider settings
4. Add credentials via Django admin or environment variables

Example with Google:

.. code-block:: python

    # config/settings/base.py
    INSTALLED_APPS = [
        ...
        "allauth.socialaccount.providers.google",
    ]

    SOCIALACCOUNT_PROVIDERS = {
        "google": {
            "SCOPE": ["profile", "email"],
            "AUTH_PARAMS": {"access_type": "online"},
        }
    }

Configure the client ID and secret in Django admin at ``/admin/socialaccount/socialapp/`` or via environment variables with provider-specific settings.

Common providers available: Google, GitHub, Microsoft, Apple, Okta, GitLab, Slack, and `many more <https://docs.allauth.org/en/latest/socialaccount/providers/index.html>`_.

Enterprise SSO (SAML/OIDC)
^^^^^^^^^^^^^^^^^^^^^^^^^^

For enterprise identity providers:

- **OIDC**: Use allauth's OpenID Connect provider (shown in the Cognito section below)
- **SAML**: Consider `python-social-auth <https://python-social-auth.readthedocs.io/>`_ or dedicated SAML libraries

Enterprise SSO typically requires attribute mapping to populate user fields and may need custom adapter logic for auto-provisioning users.

AWS Cognito Integration
-----------------------

AWS Cognito works well for applications deployed on AWS. The recommended approach uses Cognito's OAuth2/OIDC endpoint with allauth.

As OAuth Provider
^^^^^^^^^^^^^^^^^

Configure Cognito as an OpenID Connect provider:

.. code-block:: python

    # config/settings/base.py
    INSTALLED_APPS = [
        ...
        "allauth.socialaccount.providers.openid_connect",
    ]

    SOCIALACCOUNT_PROVIDERS = {
        "openid_connect": {
            "APPS": [
                {
                    "provider_id": "cognito",
                    "name": "AWS Cognito",
                    "client_id": env("COGNITO_CLIENT_ID"),
                    "secret": env("COGNITO_CLIENT_SECRET"),
                    "settings": {
                        "server_url": "https://<your-domain>.auth.<region>.amazoncognito.com",
                    },
                }
            ]
        }
    }

Replace ``<your-domain>`` and ``<region>`` with your Cognito User Pool domain and AWS region. The ``server_url`` should be your Cognito domain (found in the App Integration tab of your User Pool).

Direct SDK Integration
^^^^^^^^^^^^^^^^^^^^^^

For advanced use cases like admin operations or custom authentication flows, you can use ``boto3`` directly with the Cognito Identity Provider API. This bypasses allauth entirely and requires custom views.

For most applications, the OAuth approach above is simpler and integrates cleanly with allauth's session management and user model.

API Authentication
------------------

When ``use_drf=y`` is selected, the template configures:

- **Session authentication** for browser-based API calls (uses Django sessions)
- **Token authentication** for programmatic access (stateless tokens)
- **allauth.headless** for SPA authentication flows

Obtain and use a token:

.. code-block:: bash

    # Get a token
    curl -X POST http://localhost:8000/api/auth-token/ \
      -d "username=user@example.com" \
      -d "password=yourpassword"

    # Use the token
    curl http://localhost:8000/api/users/me/ \
      -H "Authorization: Token your-token-here"

Tokens are persistent until explicitly deleted. For SPAs using React, consider ``allauth.headless`` which provides a complete headless authentication API.

Multi-Factor Authentication
---------------------------

The template includes ``allauth.mfa`` for TOTP-based two-factor authentication. Users can enable MFA at ``/accounts/2fa/`` using any authenticator app (Google Authenticator, Authy, 1Password, etc.).

Recovery codes are generated when MFA is enabled. See the `allauth MFA documentation <https://docs.allauth.org/en/latest/mfa/index.html>`_ for configuration options.

Configuration Reference
-----------------------

Key authentication settings in ``config/settings/base.py``:

.. list-table::
   :header-rows: 1
   :widths: 35 20 45

   * - Setting
     - Default
     - Description
   * - ``ACCOUNT_ALLOW_REGISTRATION``
     - ``True``
     - Enable/disable public signup (env: ``DJANGO_ACCOUNT_ALLOW_REGISTRATION``)
   * - ``ACCOUNT_LOGIN_METHODS``
     - Based on template
     - ``{"email"}`` or ``{"username"}``
   * - ``ACCOUNT_EMAIL_VERIFICATION``
     - ``"mandatory"`` (prod)
     - Require email verification before login
   * - ``DJANGO_ADMIN_FORCE_ALLAUTH``
     - ``False``
     - Route Django admin login through allauth

See Also
--------

- :doc:`api-development` — API framework patterns and authentication details
- :doc:`multi-tenancy-organizations` — Organization-based access control building on authentication
- `django-allauth documentation <https://docs.allauth.org/>`_ — Complete allauth reference
- `DRF Authentication <https://www.django-rest-framework.org/api-guide/authentication/>`_ — Token and session authentication details
