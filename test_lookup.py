import asyncio
from equipment_poc import lookup_warranty

async def main():
    print("🚀 Starting Test Lookup...")
    # Using user-provided serial number
    result = await lookup_warranty("5434REB2F", "Trane") 
    print(f"\n✅ Test Complete. Result:\n{result}")

if __name__ == "__main__":
    asyncio.run(main())
