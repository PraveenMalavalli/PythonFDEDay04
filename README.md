# SDK vs REST API — When to Use Each

## 1. What is an SDK?

An SDK (Software Development Kit) is a library provided by an API provider to simplify communication with its services.

An SDK often handles authentication, HTTP requests, serialization, pagination, retries, and error handling.

## 2. When would I use the provider's SDK?

I would choose the provider's SDK when:

- The provider offers an official, well-maintained SDK for my programming language.
- I want faster development with less HTTP-related code.
- The SDK already handles authentication, pagination, retries, and API errors.
- I need to integrate with a complex API containing many endpoints.
- I want to reduce the maintenance burden of manually managing API changes.

**Example:** Using the official AWS SDK for Python (Boto3) to interact with Amazon S3 instead of manually constructing HTTP requests.

## 3. When would I call the REST API directly?

I would choose direct REST API calls when:

- The provider does not offer a suitable SDK.
- The SDK does not support a required endpoint or feature.
- I need greater control over HTTP headers, timeouts, retries, and request handling.
- I want to keep dependencies minimal.
- I am learning how APIs, HTTP requests, and responses work.

**Example:** Using Python HTTPX to communicate with the Training Mock API.

## 4. SDK vs REST Comparison

| Feature | Provider SDK | Direct REST API |
|---|---|---|
| Development effort | Usually lower | Usually higher |
| HTTP handling | Mostly managed by SDK | Managed by developer |
| Authentication | Often simplified | Implemented manually |
| Retries and pagination | May be built in | Must be implemented if required |
| Flexibility | Limited by SDK functionality | Direct control over requests |
| Maintenance | Depends on SDK updates | Depends on API changes |

## 5. My Decision for This Exercise

For the Training Mock API exercise, I chose **direct REST API calls using Python HTTPX** because the objective is to understand and implement reliable API communication.

My APIClient includes:

- Configurable request timeouts.
- Retries for HTTP 429 and 5xx responses.
- Exponential backoff with jitter.
- Support for the `Retry-After` header.
- Dynamic pagination using page, offset, or cursor.
- Pydantic validation of API response records.
- Offline unit testing using `httpx.MockTransport`.

Implementing these features directly helps me understand how an API client works internally.

## 6. Conclusion

I would generally prefer a well-maintained official SDK for production integrations when it meets my requirements, because it reduces repetitive implementation and maintenance work.

However, I would use direct REST calls when I need additional flexibility, unsupported endpoints, or precise control over request and response handling.

**For this exercise, direct REST calls with HTTPX are the better choice because implementing these mechanisms is part of the learning objective.**
