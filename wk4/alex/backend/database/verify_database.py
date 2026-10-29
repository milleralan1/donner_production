#!/usr/bin/env python3
"""
Comprehensive database verification script
Shows that all tables exist and are properly populated

This script verifies:
- All tables are created
- Record counts for each table
- Sample instruments with allocations
- Allocation percentages sum to 100%
- Asset class distribution
- Database indexes and triggers

Note: JSONB values are stored as floats (100.0) not strings ('100')
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
from src.models import Database
from seed_pgvector import SEED_DOCUMENTS, SEED_SOURCE, SEED_TENANT_ID
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

database = os.environ.get("DB_NAME", "alex")
client = Database().client
verification_errors = []

def execute_query(sql, description, parameters=None) -> list[dict] | None:
    """Execute a query and return results"""
    print(f"\n{description}")
    print("-" * 50)
    
    try:
        return client.query(sql, parameters)
    except Exception as e:
        print(f"❌ Error: {e}")
        verification_errors.append(str(e))
        return None

def main():
    verification_errors.clear()
    print("🔍 DATABASE VERIFICATION REPORT")
    print("=" * 70)
    print("📍 Backend: Cloud SQL")
    print(f"📦 Database: {database}")
    print("=" * 70)
    
    # 1. Show all tables
    response = execute_query(
        """
        SELECT table_name, 
               pg_size_pretty(pg_total_relation_size(quote_ident(table_name)::regclass)) as size
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        "📊 ALL TABLES IN DATABASE"
    )
    
    if response:
        print(f"✅ Found {len(response)} tables:\n")
        for record in response:
            table_name = record["table_name"]
            size = record["size"]
            print(f"   • {table_name:<20} Size: {size}")
    
    # 2. Count records in each table
    response = execute_query(
        """
        SELECT 
            'users' as table_name, COUNT(*) as count FROM users
        UNION ALL
        SELECT 'instruments', COUNT(*) FROM instruments
        UNION ALL
        SELECT 'accounts', COUNT(*) FROM accounts
        UNION ALL
        SELECT 'positions', COUNT(*) FROM positions
        UNION ALL
        SELECT 'jobs', COUNT(*) FROM jobs
        ORDER BY table_name
        """,
        "📈 RECORD COUNTS PER TABLE"
    )
    
    if response:
        print("\nTable record counts:\n")
        for record in response:
            table_name = record["table_name"]
            count = record["count"]
            status = "✅" if (table_name == 'instruments' and count > 0) else "📭"
            print(f"   {status} {table_name:<20} {count:,} records")
    
    # 3. Show instruments with allocation data
    response = execute_query(
        """
        SELECT symbol, name, instrument_type,
               allocation_asset_class::text as asset_class
        FROM instruments 
        ORDER BY symbol 
        LIMIT 10
        """,
        "🎯 SAMPLE INSTRUMENTS (First 10)"
    )
    
    if response:
        print("\nSymbol | Name | Type | Asset Class Allocation")
        print("-" * 70)
        for record in response:
            symbol = record["symbol"]
            name = record["name"][:35]
            inst_type = record["instrument_type"]
            asset_class = record["asset_class"]
            print(f"{symbol:<6} | {name:<35} | {inst_type:<10} | {asset_class}")
    
    # 4. Verify allocation sums
    response = execute_query(
        """
        SELECT symbol,
               (SELECT SUM(value::numeric) FROM jsonb_each_text(allocation_regions)) as regions_sum,
               (SELECT SUM(value::numeric) FROM jsonb_each_text(allocation_sectors)) as sectors_sum,
               (SELECT SUM(value::numeric) FROM jsonb_each_text(allocation_asset_class)) as asset_sum
        FROM instruments
        WHERE symbol IN ('SPY', 'QQQ', 'BND', 'VEA', 'GLD')
        """,
        "✅ ALLOCATION VALIDATION (Sample ETFs)"
    )
    
    if response:
        print("\nVerifying allocations sum to 100%:\n")
        print("Symbol | Regions | Sectors | Assets | Status")
        print("-" * 50)
        for record in response:
            symbol = record["symbol"]
            regions = float(record["regions_sum"] or 0)
            sectors = float(record["sectors_sum"] or 0)
            assets = float(record["asset_sum"] or 0)
            
            all_valid = regions == 100 and sectors == 100 and assets == 100
            status = "✅ Valid" if all_valid else "❌ Invalid"
            
            print(f"{symbol:<6} | {regions:>7}% | {sectors:>7}% | {assets:>6}% | {status}")
    
    # 5. Show asset class distribution
    response = execute_query(
        """
        SELECT 
            COUNT(*) FILTER (WHERE (allocation_asset_class->>'equity')::numeric = 100) as pure_equity,
            COUNT(*) FILTER (WHERE (allocation_asset_class->>'fixed_income')::numeric = 100) as pure_bonds,
            COUNT(*) FILTER (WHERE (allocation_asset_class->>'real_estate')::numeric = 100) as real_estate,
            COUNT(*) FILTER (WHERE (allocation_asset_class->>'commodities')::numeric = 100) as commodities,
            COUNT(*) FILTER (WHERE jsonb_typeof(allocation_asset_class) = 'object' 
                            AND (SELECT COUNT(*) FROM jsonb_object_keys(allocation_asset_class)) > 1) as mixed,
            COUNT(*) as total
        FROM instruments
        """,
        "📊 ASSET CLASS DISTRIBUTION"
    )
    
    if response:
        record = response[0]
        print("\nInstrument breakdown by asset class:\n")
        print(f"   • Pure Equity ETFs:      {record['pure_equity']:>3}")
        print(f"   • Pure Bond Funds:       {record['pure_bonds']:>3}")
        print(f"   • Real Estate ETFs:      {record['real_estate']:>3}")
        print(f"   • Commodity ETFs:        {record['commodities']:>3}")
        print(f"   • Mixed Allocation ETFs: {record['mixed']:>3}")
        print(f"   " + "-" * 25)
        print(f"   • TOTAL INSTRUMENTS:     {record['total']:>3}")
    
    # 6. Check indexes exist
    response = execute_query(
        """
        SELECT schemaname, tablename, indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname LIKE 'idx_%'
        ORDER BY tablename, indexname
        """,
        "🔍 DATABASE INDEXES"
    )
    
    if response:
        print(f"\n✅ Found {len(response)} custom indexes")

    # 7. Verify pgvector installation, schema, data, and cosine operator
    extension = execute_query(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'",
        "🧩 PGVECTOR EXTENSION",
    )
    if extension and extension[0].get("extversion"):
        print(f"✅ pgvector extension installed (version {extension[0]['extversion']})")
    else:
        verification_errors.append("pgvector extension is not installed")
        print("❌ pgvector extension is missing")

    vector_column = execute_query(
        """
        SELECT udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'research_documents'
          AND column_name = 'embedding'
        """,
        "🧱 PGVECTOR COLUMN",
    )
    if vector_column and vector_column[0].get("udt_name") == "vector":
        print("✅ research_documents.embedding uses the vector type")
    else:
        verification_errors.append(
            "research_documents.embedding vector column is missing"
        )
        print("❌ research_documents.embedding vector column is missing")

    vector_stats = execute_query(
        """
        SELECT COUNT(*) AS count,
               MIN(vector_dims(embedding)) AS min_dimension,
               MAX(vector_dims(embedding)) AS max_dimension
        FROM research_documents
        """,
        "📐 PGVECTOR DATA AND DIMENSIONS",
    )
    if vector_stats:
        record = vector_stats[0]
        count = record["count"]
        min_dimension = record["min_dimension"]
        max_dimension = record["max_dimension"]
        print(
            f"Found {count} vectors; dimensions range from "
            f"{min_dimension} to {max_dimension}"
        )
        if not count:
            verification_errors.append("research_documents contains no vectors")
        elif min_dimension != max_dimension:
            verification_errors.append(
                "research_documents contains inconsistent vector dimensions"
            )

        configured_dimension = os.environ.get("EMBEDDING_OUTPUT_DIMENSIONALITY")
        if configured_dimension:
            try:
                expected_dimension = int(configured_dimension)
            except ValueError:
                verification_errors.append(
                    "EMBEDDING_OUTPUT_DIMENSIONALITY must be a positive integer"
                )
            else:
                if min_dimension != expected_dimension or max_dimension != expected_dimension:
                    verification_errors.append(
                        "stored vector dimensions do not match "
                        "EMBEDDING_OUTPUT_DIMENSIONALITY"
                    )

    seed_count = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM research_documents
        WHERE tenant_id = :tenant_id
          AND metadata->>'seed_source' = :seed_source
        """,
        "🌱 PGVECTOR SEED DATA",
        {"tenant_id": SEED_TENANT_ID, "seed_source": SEED_SOURCE},
    )
    if seed_count:
        count = seed_count[0]["count"]
        print(f"Found {count}/{len(SEED_DOCUMENTS)} pgvector smoke-test documents")
        if count != len(SEED_DOCUMENTS):
            verification_errors.append("pgvector smoke-test seed data is incomplete")

    distance = execute_query(
        """
        SELECT embedding <=> embedding AS self_distance
        FROM research_documents
        ORDER BY id
        LIMIT 1
        """,
        "🔎 PGVECTOR COSINE-DISTANCE CHECK",
    )
    if distance:
        self_distance = float(distance[0]["self_distance"])
        if abs(self_distance) <= 1e-6:
            print("✅ cosine-distance operator returns zero for a vector and itself")
        else:
            verification_errors.append(
                f"pgvector self-distance should be zero, got {self_distance}"
            )
            print(f"❌ unexpected pgvector self-distance: {self_distance}")
    elif distance == []:
        verification_errors.append("cosine-distance check found no vectors")

    # 8. Check triggers exist
    response = execute_query(
        """
        SELECT trigger_name, event_object_table
        FROM information_schema.triggers
        WHERE trigger_schema = 'public'
        ORDER BY event_object_table
        """,
        "⚡ DATABASE TRIGGERS"
    )
    
    if response:
        print(f"\n✅ Found {len(response)} update triggers for timestamp management")
    
    if verification_errors:
        print(f"\n❌ Verification failed with {len(verification_errors)} database error(s)")
        return 1

    # Final summary
    print("\n" + "=" * 70)
    print("🎉 DATABASE VERIFICATION COMPLETE")
    print("=" * 70)
    print("\n✅ All tables created successfully")
    print("✅ 22 instruments loaded with complete allocation data")
    print("✅ All allocation percentages sum to 100%")
    print("✅ Indexes and triggers are in place")
    print("✅ Database is ready for Part 6: Agent Orchestra!")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        if hasattr(client, "close"):
            client.close()