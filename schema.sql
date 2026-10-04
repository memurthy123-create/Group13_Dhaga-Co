-- Run in Supabase: SQL Editor -> New query -> Run

-- 1. orders (existing table; created here only if it does not exist yet)
create table if not exists orders (
    order_id      text primary key,
    customer_name text not null,
    payment_mode  text not null check (payment_mode in ('COD', 'PREPAID')),
    address_text  text,
    pincode       text,
    order_status  text not null check (order_status in
                  ('PLACED', 'READY_TO_SHIP', 'ON_HOLD', 'SHIPPED', 'CANCEL_REQUESTED')),
    created_at    timestamptz not null default now()
);

-- If you already created orders with user_id (earlier version of this file),
-- these two lines migrate it. They are harmless on a fresh table.
alter table orders drop column if exists user_id;
alter table orders add column if not exists customer_name text;

-- 2. cod_confirmation (one row per confirmation attempt)
create table if not exists cod_confirmation (
    id                 bigint generated always as identity primary key,
    order_id           text not null references orders(order_id) on delete cascade,
    attempt_number     int  not null check (attempt_number between 1 and 2),  -- max 2 attempts
    response           text check (response in ('YES', 'NO', 'CANCEL', 'OTHER', 'NO_RESPONSE')),
    other_reason_text  text,
    address_confirmed  boolean,
    timeslot           text,
    response_time      timestamptz,
    next_retry_date    date,
    status             text not null default 'PENDING'
                       check (status in ('PENDING', 'COMPLETED', 'ESCALATED')),
    unique (order_id, attempt_number)
);

-- 3. support_tickets (human override queue)
create table if not exists support_tickets (
    ticket_id   bigint generated always as identity primary key,
    order_id    text not null references orders(order_id) on delete cascade,
    issue_type  text not null check (issue_type in
                ('CANCEL_REQUEST', 'NO_CONFIRMATION', 'CUSTOMER_QUERY')),
    created_at  timestamptz not null default now(),
    status      text not null default 'OPEN'
                check (status in ('OPEN', 'IN_PROGRESS', 'CLOSED'))
);
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
