-- customer_types definition

CREATE TABLE customer_types(
	id integer not null primary key,
	name text not null,
	created_at integer not null default (unixepoch()),
	updated_at integer
);

-- customers definition

CREATE TABLE customers(
	id text not null primary key,
	type_id integer not null references customer_types(id) on delete cascade,
	name text not null,
	created_at integer not null default (unixepoch()),
	updated_at integer
);

-- discount_records definition

CREATE TABLE discount_records(
	id integer not null primary key,
	transaction_record_id integer not null references transaction_records(id) on delete cascade,
	step integer not null,
	type text not null,
	value numeric not null,
	created_at integer not null default (unixepoch()),
	updated_at integer
	unique(transaction_record_id, step)
);

-- discounts definition

CREATE TABLE discounts(
	customer_id text not null references customers(id) on delete cascade,
	item_id text not null references items(id) on delete cascade,
	step integer not null default 1,
	type text not null,
	value numeric not null,
	created_at integer not null default (unixepoch()),
	updated_at integer
	primary key (customer_id, item_id, step)
);

-- invoices definition

CREATE TABLE invoices(
	id INTEGER PRIMARY KEY NOT NULL,
	customer_id text not null references customers(id) on delete cascade,
	transaction_id text not null unique,
	created_at integer not null default (unixepoch()),
	updated_at integer
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

-- transaction_records definition

CREATE TABLE transaction_records(
	id integer not null primary key,
	invoice_id integer not null references invoices(id) on delete cascade,
	item_id text not null references items(id) on delete cascade,
	quantity integer not null,
	created_at INTEGER NOT NULL DEFAULT (unixepoch()),
	updated_at INTEGER,
	unique(invoice_id, item_id)
);
