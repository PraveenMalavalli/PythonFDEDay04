# Provider SDK or direct REST?

**Prefer the official SDK** when it is maintained, supports the provider's API features, has
well-documented authentication, pagination and retry behavior, and fits your Python version.
The SDK reduces repetitive HTTP code and may keep up with provider API changes. Verify that
its version and security maintenance meet your project's policies.

**Use REST with HTTPX yourself** when no suitable SDK exists, when you need an endpoint or
feature missing from the SDK, when a small integration needs only a few calls, or when you
must control request/response formats, timeouts, retry behavior and transport.
The tradeoff is owning more code and tests for API versioning, HTTP errors, authentication,
rate limiting and validation.

For writes, do not retry automatically unless the endpoint is known to be idempotent or the
provider supports a documented idempotency key. This demo server supports the
`Idempotency-Key` request header; real providers may use different behavior.
