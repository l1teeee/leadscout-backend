import asyncio

from app.security import create_access_token
from app.services import auth_service


def _run(coro):
    return asyncio.run(coro)


def test_onboarding_continues_when_auth_admin_metadata_is_forbidden(mock_supabase):
    user_id = "95cc638f-dfd7-4cbb-870e-d55280eaff3c"
    email = "official.count.alejandro@gmail.com"
    token = create_access_token(user_id, email)

    mock_supabase.auth.admin.get_user_by_id.side_effect = Exception("User not allowed")
    mock_supabase.auth.admin.update_user_by_id.side_effect = Exception("User not allowed")

    user = _run(
        auth_service.complete_onboarding(
            token,
            {
                "full_name": "Alejandro",
                "workspace_name": "Scoutia",
                "industry": "Marketing",
                "country": "El Salvador",
                "city": "San Salvador",
            },
        )
    )

    workspace_payload = mock_supabase.table("workspaces").insert.call_args.args[0]
    assert "phone" not in workspace_payload
    assert "website" not in workspace_payload
    assert user.id == user_id
    assert user.email == email
    assert user.onboarded is True
    assert user.workspace_id == "test-workspace-123"
