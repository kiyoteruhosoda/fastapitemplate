"""アカウントセキュリティ・コンテキストのドメイン例外。

Presentation 層はこれらを HTTP ステータス＋エラーコードへ変換する
（表示文言への変換はフロントエンド。CLAUDE.md「国際化」参照）。
"""

from __future__ import annotations


class AccountSecurityError(Exception):
    """このコンテキストの基底例外。``code`` がそのまま API のエラーコードになる。"""

    code = "account_security_error"


class TotpAlreadyEnabledError(AccountSecurityError):
    """すでに二要素認証が有効なアカウントで登録を始めようとした。"""

    code = "totp_already_enabled"


class TotpNotEnrolledError(AccountSecurityError):
    """登録手続きが始まっていない（確認コードの検証先が無い）。"""

    code = "totp_not_enrolled"


class InvalidTotpCodeError(AccountSecurityError):
    """確認コードが一致しない。"""

    code = "invalid_totp"


class TotpRequiredError(AccountSecurityError):
    """二要素認証が有効なのにコードが提示されなかった。"""

    code = "totp_required"


class ChallengeNotFoundError(AccountSecurityError):
    """WebAuthn チャレンジが見つからない（期限切れ・使用済み・別プロセス）。"""

    code = "challenge_not_found"


class PasskeyVerificationError(AccountSecurityError):
    """WebAuthn の署名検証に失敗した。"""

    code = "passkey_verification_failed"


class PasskeyAlreadyRegisteredError(AccountSecurityError):
    """同じ資格情報が他のアカウントに登録済み。"""

    code = "passkey_already_registered"


class PasskeyNotFoundError(AccountSecurityError):
    """指定されたパスキーが存在しない（他人のものを含む）。"""

    code = "passkey_not_found"


__all__ = [
    "AccountSecurityError",
    "ChallengeNotFoundError",
    "InvalidTotpCodeError",
    "PasskeyAlreadyRegisteredError",
    "PasskeyNotFoundError",
    "PasskeyVerificationError",
    "TotpAlreadyEnabledError",
    "TotpNotEnrolledError",
    "TotpRequiredError",
]
