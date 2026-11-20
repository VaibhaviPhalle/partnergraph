import asyncio

from cognee_client import connect, disconnect, recall, remember

DATASET = "spike"

TEXTS = [
    "Acme builds vector search for RAG apps (source: https://acme.test/product)",
    "Beta is hiring an engineer to fix hallucinations in their RAG chatbot "
    "(source: https://beta.test/jobs/1)",
]

QUERY = "Why would Beta be a customer of Acme? Cite source URLs."


async def main():
    await connect()
    try:
        for t in TEXTS:
            await remember(t, DATASET)
        # Cloud remember() returns status="running"; the graph builds in the
        # background, so retry recall until the dataset is searchable.
        for attempt in range(30):
            try:
                results = await recall(QUERY, datasets=[DATASET])
                break
            except RuntimeError as e:
                if "NoDataError" not in str(e):
                    raise
                print(f"[waiting for graph build... {attempt + 1}]")
                await asyncio.sleep(10)
        else:
            raise TimeoutError("dataset never became searchable")
        for r in results:
            print(r)
    finally:
        await disconnect()


if __name__ == "__main__":
    asyncio.run(main())
