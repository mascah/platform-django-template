.. _e2e-testing-playwright:

E2E Testing with Playwright
===========================

End-to-end (E2E) tests verify complete user journeys across your application stack. While unit tests (see :doc:`testing`) validate individual components in isolation, E2E tests ensure that the Landing site, Django backend, and React SPA work together correctly.

In a monorepo with multiple frontend applications and a Django backend, E2E tests are particularly valuable for validating integration points: authentication flows, API interactions, and cross-app navigation.

When to Use E2E Tests
---------------------

E2E tests are slow and expensive compared to unit tests. Use them strategically for:

- **Critical user flows**: Login, signup, checkout, core business operations
- **Cross-app transitions**: Landing page to authenticated app, logout flows
- **Integration verification**: Frontend and backend working together correctly

Prefer unit and integration tests for edge cases, error handling, and business logic validation.

Where Playwright Fits in the Monorepo
-------------------------------------

The recommended approach is to create a dedicated ``packages/e2e/`` workspace package that tests across all applications:

.. code-block:: text

    packages/
    └── e2e/
        ├── package.json
        ├── playwright.config.ts
        ├── tests/
        │   ├── auth/           # Authentication flows
        │   ├── landing/        # Landing page tests
        │   ├── app/            # SPA tests
        │   └── cross-app/      # Tests spanning applications
        └── fixtures/           # Shared test utilities

This structure keeps E2E tests separate from application code while allowing them to test the full stack. The alternative—placing tests within each app—makes cross-app flow testing more difficult and duplicates configuration.

Turborepo Integration
^^^^^^^^^^^^^^^^^^^^^

Add E2E testing to your Turborepo workflow:

1. Add a ``test:e2e`` script to the root ``package.json``
2. Configure ``turbo.json`` to disable caching for E2E tests (they should always run fresh)
3. Ensure E2E tests depend on both frontend apps being built

Key User Flows to Test
----------------------

Focus E2E tests on the flows that matter most to your users and business.

Authentication Flows
^^^^^^^^^^^^^^^^^^^^

The authentication flow spans Django and the React SPA:

1. User clicks "Sign In" on landing page
2. Django allauth handles login at ``/accounts/login/``
3. Successful login redirects to the SPA dashboard at ``/app/``
4. The SPA's ``AuthProvider`` fetches user data from ``/api/users/me/``
5. Dashboard renders with user information

Test both the happy path and failure scenarios (invalid credentials, session expiry).

Landing to App Transitions
^^^^^^^^^^^^^^^^^^^^^^^^^^

- Marketing pages render correctly
- Call-to-action buttons navigate to authentication pages
- Unauthenticated access to ``/app/`` redirects to login
- Post-login redirect returns users to their originally requested page

SPA Functionality
^^^^^^^^^^^^^^^^^

- Dashboard loads and displays user data from the API
- Theme toggle persists user preference
- Navigation between SPA routes works correctly
- Error states display appropriately when API calls fail

Cross-App Consistency
^^^^^^^^^^^^^^^^^^^^^

- Navigation between landing site and authenticated app works smoothly
- Shared UI components from ``packages/ui/`` render consistently across apps
- Theme settings persist across applications

Handling Authentication in E2E Tests
------------------------------------

Most E2E tests require an authenticated user. There are three approaches, each with trade-offs.

Full Login Flow
^^^^^^^^^^^^^^^

Playwright fills the login form and submits it for each test. This is the most realistic but slowest approach. Use it for tests that specifically validate authentication behavior.

Session Storage Reuse (Recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Perform login once at the start of a test run, then save the browser's storage state. Subsequent tests reuse this state via Playwright's ``storageState`` option. This provides a good balance between speed and realism.

This approach works well with Django's session-based authentication since session cookies persist across requests.

API-Based Authentication
^^^^^^^^^^^^^^^^^^^^^^^^

Hit Django's authentication endpoint directly and set cookies programmatically. This is the fastest option but bypasses the frontend authentication code entirely. Use it for tests that don't focus on authentication.

Django-Specific Considerations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Django requires CSRF tokens for POST requests—ensure your test setup handles this
- Session cookies are set by Django allauth at ``/accounts/``
- For multi-domain setups, configure cookies to work across subdomains

Running Tests Against Different Environments
--------------------------------------------

Local Development
^^^^^^^^^^^^^^^^^

During local development, all services run via ``docker compose``:

- Django backend at ``localhost:8000``
- Landing app (Astro) at ``localhost:5174``
- SPA app (React) at ``localhost:5173``

Use Playwright's ``webServer`` configuration to start services before tests run, or run them manually with Docker Compose.

Staging and Production
^^^^^^^^^^^^^^^^^^^^^^

For staging environments, configure Playwright to point at deployed URLs using environment variables:

.. code-block:: typescript

    // playwright.config.ts (conceptual)
    const config = {
      use: {
        baseURL: process.env.APP_URL || 'http://localhost:5173',
      },
    };

Consider creating a dedicated test organization or user in staging environments for E2E tests. Avoid tests that depend on specific production data.

Test Data Management
^^^^^^^^^^^^^^^^^^^^

- Use Django's Factory Boy to create test fixtures
- Consider a dedicated test database for E2E runs
- Clean up test data after test runs to avoid state pollution
- Keep tests independent—each test should set up its own required state

CI/CD Integration
-----------------

E2E tests should run in your continuous integration pipeline to catch integration issues before deployment.

GitHub Actions Workflow
^^^^^^^^^^^^^^^^^^^^^^^

A typical workflow structure:

1. Build all applications (parallel builds via Turborepo)
2. Start services (Django + built frontends)
3. Run Playwright tests
4. Upload artifacts on failure (screenshots, traces)

When to Run E2E Tests
^^^^^^^^^^^^^^^^^^^^^

- **On PRs**: Run a smoke test subset for quick feedback
- **On merge to main**: Run the full E2E suite
- **Before deployments**: Gate production deployments on E2E success
- **Nightly**: Run comprehensive regression tests

Artifacts to Preserve
^^^^^^^^^^^^^^^^^^^^^

Configure your CI to save these artifacts when tests fail:

- **Screenshots**: Visual state at failure point
- **Traces**: Playwright's trace viewer data for debugging
- **Videos**: Optional, useful but storage-intensive

Best Practices
--------------

Test Organization
^^^^^^^^^^^^^^^^^

- Group tests by user journey, not by application or component
- Use the Page Object Model pattern for maintainability
- Share fixtures for common operations (login, navigation)
- Tag tests by criticality (``@critical``, ``@smoke``) for selective runs

Selector Strategy
^^^^^^^^^^^^^^^^^

- Use ``data-testid`` attributes for test-specific selectors
- Avoid selectors tied to implementation details (CSS classes, DOM structure)
- Prefer accessible selectors (roles, labels) when available

Performance
^^^^^^^^^^^

- Limit E2E tests to critical paths—don't duplicate unit test coverage
- Use parallel test execution for independent test groups
- Mock external services (payment providers, third-party APIs) to avoid flakiness
- Test against built output in CI, not development servers

Debugging Failures
^^^^^^^^^^^^^^^^^^

- Use Playwright's trace viewer for CI failures
- Run with ``--headed`` locally for visual debugging
- Add meaningful test names and failure messages
- Use ``test.step()`` to document complex test flows

Anti-Patterns to Avoid
^^^^^^^^^^^^^^^^^^^^^^

- Testing implementation details that may change
- Tests that depend on execution order
- Hard-coded waits instead of explicit waits for elements/conditions
- Flaky tests that sometimes pass and sometimes fail

See Also
--------

- :doc:`testing` — Unit testing with pytest (backend)
- :doc:`type-safe-api-integration` — API client generation and type safety
- :doc:`/0-introduction/ui-architecture-philosophy` — Frontend architecture overview

.. seealso::

   - `Playwright Documentation <https://playwright.dev/docs/intro>`_
   - `Playwright Best Practices <https://playwright.dev/docs/best-practices>`_
