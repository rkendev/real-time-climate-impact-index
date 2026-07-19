"""Core package: portable, vendor-free domain logic.

INV-4 (ADR-0004): no cloud-vendor SDK may be imported anywhere under this
package. All vendor specifics live behind the transport and store adapters.
Enforced by tests/portability/test_no_cloud_sdk_import.py (AT-10).
"""
