from __future__ import annotations

import json
import random
import urllib.parse
from typing import Any, List

import requests
from django.core.exceptions import BadRequest

from openid.enums import RevocationTypes
from project import settings

from .abstractions import AOpenidService
from .models import IssuanceFlow, IssuanceInformation, VerifyFlow
from .serializers import (
    AuthorizationServerSerializer,
    ClaimsVerificationSerializer,
    CreatedDirectPostSerializer,
    CredentialIssuerSerializer,
    IssuanceCredentialOfferSerializer,
    IssuanceFlowSerializer,
    IssuanceOfferResponse,
    PresentationOfferJsonResponse,
    PresentationResponse,
    ResponseSerializer,
    VerifyFlowSerializer,
)


class OpenidService(AOpenidService):
    @staticmethod
    def get_credential_offer_by_pk(
        pk: str, pre_authorized_code: str | None, user_pin_required: bool | None
    ) -> dict | IssuanceOfferResponse | None:
        offer = IssuanceInformation.objects.filter(pk=pk).first()

        if not offer:
            return None
        else:
            credential_offer = {
                "credential_issuer": f"{settings.BACKEND_DOMAIN}",
                "credentials": offer.credential_issuer_metadata[
                    "credentials_supported"
                ],
            }
            if pre_authorized_code:
                user_pin_required = (
                    bool(json.loads(user_pin_required))
                    if user_pin_required is not None
                    else False
                )
                credential_offer["grants"] = {
                    "urn:ietf:params:oauth:grant-type:pre-authorized_code": {
                        "pre-authorized_code": pre_authorized_code,
                        "user_pin_required": user_pin_required,
                    }
                }
            else:
                credential_offer["grants"] = {"authorization_code": {}}

            return {"credential_offer": credential_offer}

    @staticmethod
    def get_credential_offer_by_issuer(
        pre_authorized_code: str | None,
        user_pin_required: bool | None,
    ) -> dict | IssuanceCredentialOfferSerializer | None:
        offer: IssuanceInformation = IssuanceInformation.objects.get()
        url = f"{settings.BACKEND_DOMAIN}/offers/{str(offer.pk)}"

        if pre_authorized_code:
            req = requests.models.PreparedRequest()
            req.prepare_url(
                url,
                {
                    "pre-authorized_code": pre_authorized_code,
                    "user_pin_required": user_pin_required,
                },
            )
            url = req.url
        get_offer_uri = urllib.parse.quote_plus(url)
        complete_url = (
            f"openid-credential-offer://?credential_offer_uri={get_offer_uri}"
        )
        pin = None
        if user_pin_required == "true":
            pin = "".join(["{}".format(random.randint(0, 9)) for num in range(0, 4)])

        return {"credential_offer": complete_url, "pin": pin}

    @staticmethod
    def get_credential_issuer_metadata_by_issuer() -> CredentialIssuerSerializer | None:
        metadata = IssuanceInformation.objects.filter().first()

        return metadata.credential_issuer_metadata

    @staticmethod
    def get_authorization_server_metadata() -> AuthorizationServerSerializer | None:
        url = f"{settings.VC_SERVICE_URL}/auth/.well-known/openid-configuration"

        params = {
            "issuerUri": f"{settings.BACKEND_DOMAIN}",
        }

        try:
            response = requests.request("GET", url, params=params)
        except Exception as e:
            raise Exception(e)

        if response.status_code == 200:
            content = json.loads(response.content.decode("utf-8"))
            return_dict = content

            return return_dict
        else:
            raise BadRequest({"status_code": response.status_code})

    @staticmethod
    def _get_verifiers_metadata_scopes_by_issuer() -> List[str]:
        scope_actions = VerifyFlow.objects.filter()
        result = []
        for action in scope_actions:
            result.append(action.scope)
        return result

    @staticmethod
    def authorize(
        request: Any,
    ) -> ResponseSerializer | None:
        url = f"{settings.VC_SERVICE_URL}/auth/authorize"
        request_get = request.GET
        request = request_get.get("request")
        if request is None:
            params = {
                "response_type": request_get["response_type"],
                "scope": request_get["scope"],
                "issuer_state": request_get.get("issuer_state"),
                "state": request_get["state"],
                "client_id": request_get["client_id"],
                "redirect_uri": request_get["redirect_uri"],
                "nonce": request_get.get("nonce"),
                "code_challenge": request_get.get("code_challenge"),
                "code_challenge_method": request_get.get("code_challenge_method"),
                "authorization_details": request_get.get("authorization_details"),
                "client_metadata": request_get["client_metadata"],
                "expectedIssuerState": request_get.get("issuer_state"),
            }
        else:
            params = request_get.dict()

        params["issuerUri"] = f"{settings.BACKEND_DOMAIN}"
        params["privateKeyJwk"] = json.dumps(settings.PRIVATE_KEY)
        params["publicKeyJwk"] = json.dumps(settings.PUBLIC_KEY)

        try:
            response = requests.request("GET", url, params=params)
        except Exception as e:
            raise Exception(e)

        content = json.loads(response.content.decode("utf-8"))

        return_dict = {"status_code": response.status_code, "content": content}
        return return_dict

    @staticmethod
    def direct_post(
        request: CreatedDirectPostSerializer,
    ) -> ResponseSerializer:
        url = f"{settings.VC_SERVICE_URL}/auth/direct_post"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        payload = {
            "issuerUri": f"{settings.BACKEND_DOMAIN}",
            "privateKeyJwk": json.dumps(settings.PRIVATE_KEY),
            "vp_token": request.get("vp_token") or None,
            "id_token": request.get("id_token") or None,
            "presentation_submission": request.get("presentation_submission") or None,
        }

        try:
            response = requests.request("POST", url, headers=headers, data=payload)
        except Exception as e:
            raise Exception(e)

        content = json.loads(response.content.decode("utf-8"))

        return_dict = {"status_code": response.status_code, "content": content}

        return return_dict

    @staticmethod
    def token_request(
        request: Any,
    ) -> ResponseSerializer:
        url = f"{settings.VC_SERVICE_URL}/auth/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        payload = {
            "grant_type": request.get("grant_type"),
            "client_id": request.get("client_id"),
            "code": request.get("code") or None,
            "code_verifier": request.get("code_verifier") or None,
            "pre-authorized_code": request.get("pre-authorized_code") or None,
            "user_pin": request.get("user_pin") or None,
            "client_assertion": request.get("client_assertion") or None,
            "client_assertion_type": request.get("client_assertion_type") or None,
            "issuerUri": f"{settings.BACKEND_DOMAIN}",
            "privateKeyJwk": json.dumps(settings.PRIVATE_KEY),
            "publicKeyJwk": json.dumps(settings.PUBLIC_KEY),
        }

        try:
            response = requests.request(
                "POST",
                url,
                headers=headers,
                data=payload,
            )
        except Exception as e:
            raise Exception(e)

        content = json.loads(response.content.decode("utf-8"))

        return_dict = {"status_code": response.status_code, "content": content}
        return return_dict

    @staticmethod
    def get_public_jwk_by_issuer() -> dict | None:
        public_key_jwk = settings.PUBLIC_KEY
        response = {
            "keys": [
                {
                    "kty": public_key_jwk["kty"],
                    "crv": public_key_jwk["crv"] or None,
                    "alg": public_key_jwk["alg"],
                    "x": public_key_jwk["x"] or None,
                    "y": public_key_jwk["y"] or None,
                    "kid": public_key_jwk["kid"],
                }
            ]
        }
        return response

    @staticmethod
    def get_claims_validation(data: Any) -> ClaimsVerificationSerializer:
        entity_url = settings.ENTITY_URL
        entity_api_key = settings.ENTITY_API_KEY

        if not entity_url and settings.DEVELOPER_MOCKUP_ENTITIES:
            # Return empty data
            content = {"verified": True}
        else:
            headers = {}
            if entity_api_key:
                headers = {"Authorization": entity_api_key}
            try:
                response = requests.request(
                    "POST",
                    entity_url + "/presentations/external-data",
                    headers=headers,
                    json=data,
                )
                content = json.loads(response.content.decode("utf-8"))
            except Exception as e:
                raise Exception(e)

        return content

    @staticmethod
    def exchange_preauth(code: str, pin: int) -> dict:
        entity_url = settings.ENTITY_URL
        entity_api_key = settings.ENTITY_API_KEY

        params = {"pin": pin}
        if entity_api_key:
            headers = {"Authorization": entity_api_key}
        try:
            response = requests.request(
                "GET",
                f"{entity_url}/preauth/exchange/{code}",
                params=params,
                headers=headers,
            )
        except Exception as e:
            raise Exception(e)

        content = json.loads(response.content.decode("utf-8"))

        return_dict = {"status_code": response.status_code, "content": content}
        return return_dict

    @staticmethod
    def retrieve_issuance_flow(vc_type: str) -> dict | None:
        issuance_flow = IssuanceFlow.objects.filter(
            credential_types=vc_type,
        ).first()
        if not issuance_flow:
            return {
                "status_code": 404,
                "content": "Unssuported requested credential",
            }
        model_response = IssuanceFlowSerializer(issuance_flow).data
        if model_response.get("revocation"):
            model_response["revocation"] = RevocationTypes[
                model_response["revocation"]
            ].value
        return {"status_code": 200, "content": model_response}

    @staticmethod
    def create_presentation_offer(
        id: str,
        state: str | None,
    ) -> dict | PresentationOfferJsonResponse | None:
        offer = VerifyFlow.objects.filter(id=id).first()

        url = f"{settings.VC_SERVICE_URL}/auth/presentation-offer"

        payload = {
            "issuerUri": f"{settings.BACKEND_DOMAIN}",
            "privateKeyJwk": json.dumps(settings.PRIVATE_KEY),
            "publicKeyJwk": json.dumps(settings.PUBLIC_KEY),
            "verify_flow": VerifyFlowSerializer(offer).data,
        }
        if state:
            payload["state"] = state

        try:
            response = requests.request("POST", url, json=payload)
        except Exception as e:
            raise Exception(e)

        content = json.loads(response.content.decode("utf-8"))

        return_dict = {"status_code": response.status_code, "content": content}
        return return_dict

    @staticmethod
    def get_presentation_offer_url(
        verify_flow: str,
        state: str | None,
    ) -> dict | PresentationResponse | None:
        offer = VerifyFlow.objects.filter(
            scope=verify_flow,
        ).first()
        url = f"{settings.BACKEND_DOMAIN}/{str(offer.id)}/presentation-offer"

        if state:
            req = requests.models.PreparedRequest()
            req.prepare_url(
                url,
                {
                    "state": state,
                },
            )
            url = req.url
        get_offer_uri = urllib.parse.quote_plus(url)
        complete_url = f"openid://?request_uri={get_offer_uri}"

        return {"presentation_offer": complete_url}
