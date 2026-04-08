-- Baseline Rouge schema for Supabase CLI migrations.
--
-- This migration represents the current desired schema after the historical
-- Yoyo migrations. Apply it to fresh/local databases. For an existing
-- data-bearing cloud database, verify the live schema first and mark this
-- version as applied instead of running it.

create table public.issues (
    id serial primary key,
    title text,
    description text not null,
    status text default 'pending' check (
        status in ('pending', 'claimed', 'started', 'completed', 'failed')
    ),
    assigned_to text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    type text not null default 'full' check (
        type in ('full', 'patch', 'thin', 'direct')
    ),
    adw_id text,
    branch text
);

create table public.comments (
    id serial primary key,
    issue_id integer not null references public.issues(id) on delete cascade,
    comment text not null,
    raw jsonb not null default '{}'::jsonb,
    source text,
    type text,
    created_at timestamptz default now(),
    adw_id text
);

create index idx_issues_status on public.issues(status);
create index idx_issues_assigned_to on public.issues(assigned_to);
create index idx_issues_type on public.issues(type);
create index idx_issues_adw_id on public.issues(adw_id);
create index idx_comments_issue_id on public.comments(issue_id);

create or replace function public.update_updated_at_column()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger update_issues_updated_at
before update on public.issues
for each row execute function public.update_updated_at_column();

create or replace function public.get_and_lock_next_issue(p_worker_id text)
returns table (
    issue_id integer,
    issue_description text,
    issue_status text,
    issue_type text,
    issue_adw_id text
) as $$
begin
    return query
    with next_issue as (
        select i.id
        from public.issues i
        where i.type in ('direct', 'full', 'patch', 'thin')
          and i.status = 'pending'
          and i.assigned_to = p_worker_id
        order by i.id
        for update skip locked
        limit 1
    )
    update public.issues i
    set status = 'claimed',
        updated_at = now()
    from next_issue
    where i.id = next_issue.id
    returning i.id, i.description, i.status, i.type, i.adw_id;
end;
$$ language plpgsql;

