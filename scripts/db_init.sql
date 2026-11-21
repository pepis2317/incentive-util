-- customers definition

CREATE TABLE customers(
	id text not null primary key,
	name text not null,
	created_at INTEGER NOT NULL DEFAULT (unixepoch()),
	updated_at INTEGER
);

-- discount_record_snapshots definition

CREATE TABLE discount_record_snapshots(
	id integer not null primary key,
	transaction_record_snapshot_id integer not null references transaction_record_snapshots(id) on delete cascade,
	step integer not null,
	value numeric not null,
	type text not null,
	created_at integer not null default (unixepoch())
);

-- discount_records definition

CREATE TABLE discount_records(
	id integer not null primary key,
	transaction_record_id integer not null references transaction_records(id) on delete cascade,
	step integer not null,
	type text not null,
	value numeric not null,
	created_at INTEGER NOT NULL DEFAULT (unixepoch()),
	updated_at INTEGER,
	unique(transaction_record_id, step)
);

-- invoice_snapshots definition

CREATE TABLE invoice_snapshots(
	id integer not null primary key,
	invoice_id integer not null references invoices(id) on delete cascade,
	customer_id text not null references customers(id) on delete cascade,
	type text not null,
	transaction_id text not null,
	created_at integer not null default (unixepoch())
);

-- invoices definition

CREATE TABLE invoices(
	id INTEGER PRIMARY KEY NOT NULL,
	customer_id text not null references customers(id) on delete cascade,
	type text not null,
	transaction_id text not null unique,
	created_at INTEGER NOT NULL DEFAULT (unixepoch()),
	updated_at INTEGER
);

-- items definition

CREATE TABLE items (
	id text primary key not null,
	name text not null,
	type text not null,
	brand text not null,
	unit text not null,
	base_price numeric not null,
	sell_price numeric not null,
	created_at integer not null default (unixepoch()),
	updated_at integer
);

-- transaction_record_snapshots definition

CREATE TABLE transaction_record_snapshots(
	id integer not null primary key,
	invoice_snapshot_id integer not null references invoice_snapshots(id) on delete cascade,
	item_id text not null references items(id) on delete cascade,
	quantity integer not null,
	price_snapshot numeric not null,
	created_at integer not null default (unixepoch())
);

-- transaction_records definition

CREATE TABLE transaction_records(
	id integer not null primary key,
	invoice_id integer not null references invoices(id) on delete cascade,
	item_id text not null references items(id) on delete cascade,
	quantity integer not null,
	price_snapshot numeric not null,
	created_at INTEGER NOT NULL DEFAULT (unixepoch()),
	updated_at INTEGER,
	unique(invoice_id, item_id)
);