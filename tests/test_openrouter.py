import os
import asyncio

# Ensure env key is set from process environment
from app.services.llm_reasoner import build_llm_reasoner_or_none

r = build_llm_reasoner_or_none()
print('REASONER:', type(r).__name__ if r else None)

async def run_test():
    if not r:
        print('No reasoner available')
        return
    try:
        res = await r.summarize('Short test transcript about edge-case behavior')
        # ReasonerResult stores the text in `.content`
        print('SUMMARY (source=%s):' % getattr(res, 'source', None))
        print(res.content[:800])
    except Exception as exc:
        import traceback
        print('ERROR running summarize():', exc)
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(run_test())
