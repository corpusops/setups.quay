
DISCLAIMER - ABANDONED/UNMAINTAINED CODE / DO NOT USE
=======================================================
While this repository has been inactive for some time, this formal notice, issued on **December 10, 2024**, serves as the official declaration to clarify the situation. Consequently, this repository and all associated resources (including related projects, code, documentation, and distributed packages such as Docker images, PyPI packages, etc.) are now explicitly declared **unmaintained** and **abandoned**.

I would like to remind everyone that this project’s free license has always been based on the principle that the software is provided "AS-IS", without any warranty or expectation of liability or maintenance from the maintainer.
As such, it is used solely at the user's own risk, with no warranty or liability from the maintainer, including but not limited to any damages arising from its use.

Due to the enactment of the Cyber Resilience Act (EU Regulation 2024/2847), which significantly alters the regulatory framework, including penalties of up to €15M, combined with its demands for **unpaid** and **indefinite** liability, it has become untenable for me to continue maintaining all my Open Source Projects as a natural person.
The new regulations impose personal liability risks and create an unacceptable burden, regardless of my personal situation now or in the future, particularly when the work is done voluntarily and without compensation.

**No further technical support, updates (including security patches), or maintenance, of any kind, will be provided.**

These resources may remain online, but solely for public archiving, documentation, and educational purposes.

Users are strongly advised not to use these resources in any active or production-related projects, and to seek alternative solutions that comply with the new legal requirements (EU CRA).

**Using these resources outside of these contexts is strictly prohibited and is done at your own risk.**

Regarding the potential transfer of the project to another entity, discussions are ongoing, but no final decision has been made yet. As a last resort, if the project and its associated resources are not transferred, I may begin removing any published resources related to this project (e.g., from PyPI, Docker Hub, GitHub, etc.) starting **March 15, 2025**, especially if the CRA’s risks remain disproportionate.


# docker based quay fullstack deployment using ansible
See playbooks, set your variables and enjoy

ETA: WIP/not finished, may not be done

we didnt validated the solution (leaks in object storage, overall stability)


- can be used behind a SSL offloader
- adds a fail2ban integration to ban brute force attacks



To store in ovh PCS, we needed to patch the cloud s3 backend this way
```python
/quay-registry/storage/cloud.py
 
class S3Storage(_CloudStorage):
    def __init__(
        self,
        context,
        storage_path,
        s3_bucket,
        s3_access_key=None,
        s3_secret_key=None,
        # Boto2 backward compatible options (host excluding scheme or port)
        host=None,
        port=None,
        # Boto3 options (Full url including scheme anbd optionally port)
        endpoint_url=None,
        encryption=True,
        config=None,
        upload_params=None,
    ):
        if config is None:
            config = {}
        if upload_params is None:
            upload_params = {}
        if encryption:
            upload_params.setdefault("ServerSideEncryption", "AES256")
        config.setdefault("signature_version", "s3v4")
        connect_kwargs = {"config": Config(**config)}
        if host or endpoint_url:
            connect_kwargs["endpoint_url"] = endpoint_url or _build_endpoint_url(
                host, port=port, is_secure=True
            )                                      
```
