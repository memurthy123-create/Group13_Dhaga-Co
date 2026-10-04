-- Run once in your Supabase SQL editor. Only the server-side service_role can access.
create table if not exists public.return_records (
 record_id text primary key,
 raw jsonb not null,
 input_hash text not null,
 decision jsonb,
 previous_decision jsonb,
 status text not null check (status in ('ready','needs_review','approved','failed')),
 reviewed_by text,
 review_note text not null default '',
 engine text not null,
 error text not null default '',
 reviewer_used boolean not null default false,
 updated_at timestamptz not null default now()
);
create table if not exists public.catalogue_records (like public.return_records including all);
create table if not exists public.review_log (
 id bigint generated always as identity primary key,
 task text not null check (task in ('returns','catalogue')),
 record_id text not null,
 before_decision jsonb,
 after_decision jsonb not null,
 reviewed_by text not null,
 review_note text not null,
 reviewed_at timestamptz not null default now()
);
alter table public.return_records enable row level security;
alter table public.catalogue_records enable row level security;
alter table public.review_log enable row level security;
revoke all on public.return_records, public.catalogue_records, public.review_log from anon, authenticated;
grant all on public.return_records, public.catalogue_records, public.review_log to service_role;
grant usage, select on sequence public.review_log_id_seq to service_role;

create or replace function public.dhaga_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
drop trigger if exists dhaga_return_timestamp on public.return_records;
create trigger dhaga_return_timestamp before update on public.return_records for each row execute function public.dhaga_updated_at();
drop trigger if exists dhaga_catalogue_timestamp on public.catalogue_records;
create trigger dhaga_catalogue_timestamp before update on public.catalogue_records for each row execute function public.dhaga_updated_at();

-- Atomic human review: record update and audit insertion succeed or fail together.
create or replace function public.save_dhaga_review(p_task text, p_record jsonb, p_before jsonb)
returns void language plpgsql security invoker set search_path = public as $$
declare target text;
begin
 if p_task not in ('returns','catalogue') then raise exception 'Invalid task'; end if;
 if coalesce(p_record->>'reviewed_by','') = '' then raise exception 'Reviewer required'; end if;
 target := case when p_task = 'returns' then 'return_records' else 'catalogue_records' end;
 execute format('insert into public.%I (record_id, raw, input_hash, decision, previous_decision, status, reviewed_by, review_note, engine, error, reviewer_used)
 select record_id, raw, input_hash, decision, previous_decision, status, reviewed_by, review_note, engine, error, reviewer_used
 from jsonb_populate_record(null::public.%I, $1)
 on conflict (record_id) do update set raw=excluded.raw, input_hash=excluded.input_hash,
 decision=excluded.decision, previous_decision=excluded.previous_decision, status=excluded.status,
 reviewed_by=excluded.reviewed_by, review_note=excluded.review_note, engine=excluded.engine,
 error=excluded.error, reviewer_used=excluded.reviewer_used', target, target) using p_record;
 insert into public.review_log(task, record_id, before_decision, after_decision, reviewed_by, review_note)
 values(p_task, p_record->>'record_id', p_before, p_record->'decision', p_record->>'reviewed_by', p_record->>'review_note');
end $$;
revoke execute on function public.save_dhaga_review(text,jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.save_dhaga_review(text,jsonb,jsonb) to service_role;
