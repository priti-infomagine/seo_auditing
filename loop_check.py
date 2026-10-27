import asyncio
import threading

async def show_loop(label):
    loop = asyncio.get_running_loop()

    print(
        f"{label}: "
        f"thread={threading.current_thread().name}, "
        f"loop_id={id(loop)}"
    )

def run_in_temporary_loop():
    async def main():
        await show_loop("Temporary loop")

    asyncio.run(main())

async def main():
    await show_loop("Main loop")

run_in_temporary_loop()
asyncio.run(main())