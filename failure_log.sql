-- Run once in Supabase: SQL Editor -> New query -> Run
-- 4. failure_log (every failure state is stored here - guardrail G6 "fail visibly")
create table if not exists failure_log (
    id              bigint generated always as identity primary key,
    order_id        text references orders(order_id) on delete cascade,  -- null for a bulk send failure
    attempt_number  int,
    failure_type    text not null check (failure_type in
                    ('SEND_FAILURE', 'BULK_SEND_FAILURE', 'NO_RESPONSE',
                     'ADDRESS_REJECTED', 'MAX_ATTEMPTS')),
    message         text not null,
    resolved        boolean not null default false,
    created_at      timestamptz not null default now()
);
