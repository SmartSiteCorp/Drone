CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ======================
-- Devices
-- ======================

CREATE TABLE IF NOT EXISTS devices (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL,
  type text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT devices_type_chk CHECK (type IN ('relay', 'drone', 'client','dashboard', 'server'))
);

CREATE INDEX IF NOT EXISTS devices_type_idx ON devices(type);

-- ======================
-- API Keys
-- ======================

CREATE TABLE IF NOT EXISTS api_keys (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  device_id uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  key_prefix text NOT NULL,
  key_hash text NOT NULL,
  scopes text[] NOT NULL DEFAULT ARRAY[]::text[],
  revoked_at timestamptz NULL,
  expires_at timestamptz NULL,
  last_used_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS api_keys_key_prefix_idx ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS api_keys_device_id_idx ON api_keys(device_id);

-- ==============================
-- Relay <-> Drone associations
-- ==============================

CREATE TABLE IF NOT EXISTS relay_drone_links (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  relay_device_id uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  drone_device_id uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz NULL,
  revoked_reason text NULL
);

-- Un drone ne peut avoir qu’un seul relay actif
CREATE UNIQUE INDEX IF NOT EXISTS relay_drone_links_one_active_relay_per_drone
ON relay_drone_links (drone_device_id)
WHERE active = true AND revoked_at IS NULL;

-- Empêche doublon actif exact
CREATE UNIQUE INDEX IF NOT EXISTS relay_drone_links_unique_pair_active
ON relay_drone_links (relay_device_id, drone_device_id)
WHERE active = true AND revoked_at IS NULL;

-- Index performance
CREATE INDEX IF NOT EXISTS relay_drone_links_relay_idx
ON relay_drone_links (relay_device_id)
WHERE active = true AND revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS relay_drone_links_drone_idx
ON relay_drone_links (drone_device_id)
WHERE active = true AND revoked_at IS NULL;