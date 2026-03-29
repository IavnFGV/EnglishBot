from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

PERMISSION_WORDS_ADD = "words.add"
PERMISSION_WORDS_EDIT = "words.edit"
PERMISSION_WORD_IMAGES_EDIT = "words.images.edit"


@dataclass(frozen=True)
class TelegramCommandSpec:
    command: str
    description: str
    required_permission: str | None = None
    show_in_chat_menu: bool = True


DEFAULT_TELEGRAM_COMMAND_SPECS: tuple[TelegramCommandSpec, ...] = (
    TelegramCommandSpec("start", "Open personal start menu"),
    TelegramCommandSpec("help", "Show commands"),
    TelegramCommandSpec("version", "Show bot version"),
    TelegramCommandSpec("words", "Open words menu"),
    TelegramCommandSpec("assign", "Open assignments menu"),
    TelegramCommandSpec(
        "add_words",
        "Add words from raw text",
        required_permission=PERMISSION_WORDS_ADD,
    ),
    TelegramCommandSpec(
        "cancel",
        "Cancel current add-words flow",
        required_permission=PERMISSION_WORDS_ADD,
    ),
)


@dataclass(frozen=True)
class TelegramMenuAccessPolicy:
    """Centralized Telegram adapter access policy.

    The policy resolves user roles and permissions and can be extended by adding
    memberships/permissions to the injected maps.
    """

    role_memberships: Mapping[str, frozenset[int]]
    role_permissions: Mapping[str, frozenset[str]]

    @classmethod
    def from_bot_data(cls, bot_data: Mapping[str, object]) -> "TelegramMenuAccessPolicy":
        memberships_raw = bot_data.get("menu_role_memberships")
        permissions_raw = bot_data.get("menu_role_permissions")

        role_memberships = _normalize_memberships(memberships_raw)
        if role_memberships is None:
            repository_memberships = _memberships_from_role_repository(
                bot_data.get("telegram_user_role_repository")
            )
            if repository_memberships is not None:
                role_memberships = repository_memberships
            else:
                role_memberships = {
                    "admin": frozenset(_to_int_set(bot_data.get("admin_user_ids"))),
                    "editor": frozenset(_to_int_set(bot_data.get("editor_user_ids"))),
                }

        role_permissions = _normalize_permissions(permissions_raw)
        if role_permissions is None:
            role_permissions = {
                "admin": frozenset({"*"}),
                "editor": frozenset(
                    {
                        PERMISSION_WORDS_ADD,
                        PERMISSION_WORDS_EDIT,
                        PERMISSION_WORD_IMAGES_EDIT,
                    }
                ),
                "user": frozenset(),
            }

        return cls(role_memberships=role_memberships, role_permissions=role_permissions)

    def roles_for_user(self, user_id: int | None) -> tuple[str, ...]:
        if user_id is None:
            return ("user",)
        resolved = ["user"]
        for role_name, user_ids in self.role_memberships.items():
            if user_id in user_ids and role_name != "user":
                resolved.append(role_name)
        return tuple(resolved)

    def has_permission(self, user_id: int | None, permission: str) -> bool:
        for role in self.roles_for_user(user_id):
            role_perms = self.role_permissions.get(role, frozenset())
            if "*" in role_perms or permission in role_perms:
                return True
        return False

    def visible_commands(
        self,
        user_id: int | None,
        *,
        command_specs: tuple[TelegramCommandSpec, ...] = DEFAULT_TELEGRAM_COMMAND_SPECS,
        only_chat_menu: bool = False,
    ) -> tuple[TelegramCommandSpec, ...]:
        visible: list[TelegramCommandSpec] = []
        for spec in command_specs:
            if only_chat_menu and not spec.show_in_chat_menu:
                continue
            if spec.required_permission and not self.has_permission(user_id, spec.required_permission):
                continue
            visible.append(spec)
        return tuple(visible)


def _to_int_set(value: object) -> set[int]:
    if not isinstance(value, (set, tuple, list, frozenset)):
        return set()
    result: set[int] = set()
    for item in value:
        if isinstance(item, int):
            result.add(item)
    return result


def _normalize_memberships(value: object) -> dict[str, frozenset[int]] | None:
    if not isinstance(value, Mapping):
        return None
    memberships: dict[str, frozenset[int]] = {}
    for role_name, ids in value.items():
        if not isinstance(role_name, str):
            continue
        memberships[role_name] = frozenset(_to_int_set(ids))
    if "user" not in memberships:
        memberships["user"] = frozenset()
    return memberships


def _normalize_permissions(value: object) -> dict[str, frozenset[str]] | None:
    if not isinstance(value, Mapping):
        return None
    permissions: dict[str, frozenset[str]] = {}
    for role_name, role_permissions in value.items():
        if not isinstance(role_name, str):
            continue
        if isinstance(role_permissions, (set, tuple, list, frozenset)):
            normalized = {
                permission
                for permission in role_permissions
                if isinstance(permission, str) and permission.strip()
            }
        else:
            normalized = set()
        permissions[role_name] = frozenset(normalized)
    if "user" not in permissions:
        permissions["user"] = frozenset()
    return permissions


def _memberships_from_role_repository(value: object) -> dict[str, frozenset[int]] | None:
    list_memberships = getattr(value, "list_memberships", None)
    if not callable(list_memberships):
        return None
    try:
        memberships = list_memberships()
    except Exception:  # noqa: BLE001
        return None
    return _normalize_memberships(memberships)
