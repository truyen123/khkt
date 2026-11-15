#!/usr/bin/env python3
"""Test available Microsoft Edge TTS voices for Vietnamese."""
import asyncio
import edge_tts

async def test():
    # Test available Vietnamese voices
    voices = ["vi-VN-HoaiMyNeural", "vi-VN-LinhNeural", "vi-VN-NamMinNeural"]
    
    print("Testing Vietnamese voices...")
    for voice in voices:
        print(f"\n✓ Testing voice: {voice}")
        try:
            communicate = edge_tts.Communicate("Xin chào, đây là giọng nói tiếng Việt", voice=voice)
            await asyncio.wait_for(communicate.save("test.mp3"), timeout=10)
            print(f"  ✓ {voice} works!")
        except Exception as e:
            print(f"  ✗ {voice} failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
