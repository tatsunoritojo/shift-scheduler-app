-- onedrop202507@gmail.com の本番DB登録状況を読み取り専用で確認する。
-- READ ONLY トランザクションで包むため、誤って書き込んでも物理的に拒否される。
-- 実行例: psql "<DATABASE_URL>" -v ON_ERROR_STOP=1 -f docs/notes/260602_onedrop-login-readonly.sql

BEGIN TRANSACTION READ ONLY;

-- 1) users 行の有無と状態
SELECT id, email, google_id, role, is_active, organization_id, created_at, updated_at
  FROM users
 WHERE email = 'onedrop202507@gmail.com';

-- 2) user_tokens（refresh_token の有無と保存済み scope）
SELECT ut.user_id,
       ut.scopes,
       (ut.refresh_token IS NOT NULL) AS has_refresh_token,
       ut.updated_at
  FROM user_tokens ut
  JOIN users u ON u.id = ut.user_id
 WHERE u.email = 'onedrop202507@gmail.com';

-- 3) organization_members（組織紐づきと is_active）
SELECT om.user_id, om.organization_id, om.role, om.is_active, o.name
  FROM organization_members om
  JOIN users u ON u.id = om.user_id
  LEFT JOIN organizations o ON o.id = om.organization_id
 WHERE u.email = 'onedrop202507@gmail.com';

ROLLBACK;
