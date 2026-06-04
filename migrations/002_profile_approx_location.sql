-- Approximate user location.
-- Coordinates are intentionally rounded by the backend before saving.
alter table profiles
  add column if not exists approximate_latitude double precision,
  add column if not exists approximate_longitude double precision,
  add column if not exists approximate_location_label text,
  add column if not exists location_updated_at timestamptz;

create index if not exists profiles_workspace_location_idx
  on profiles(workspace_id, approximate_latitude, approximate_longitude);
