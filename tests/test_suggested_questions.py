import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.response.suggested_questions import SuggestedQuestionGenerator
from src.libs.llm.base_llm import ChatResponse
from src.core.settings import load_settings

class TestSuggestedQuestions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = load_settings()
        self.mock_llm = MagicMock()
        # Use AsyncMock for the chat method
        self.mock_llm.chat = AsyncMock()
        self.generator = SuggestedQuestionGenerator(self.settings, llm=self.mock_llm)

    async def test_parse_clean_json(self):
        # Mock successful JSON response
        self.mock_llm.chat.return_value = ChatResponse(
            content='["问题1", "问题2", "问题3"]',
            model="test-model"
        )
        
        questions = await self.generator.generate("test query", "test answer")
        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0], "问题1")

    async def test_parse_markdown_json(self):
        # Mock JSON wrapped in markdown blocks
        self.mock_llm.chat.return_value = ChatResponse(
            content='这是推荐的问题：\n```json\n["Q1", "Q2", "Q3"]\n```\n希望有帮助。',
            model="test-model"
        )
        
        questions = await self.generator.generate("test query", "test answer")
        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0], "Q1")

    async def test_parse_malformed_json(self):
        # Mock malformed JSON (should return empty list gracefully)
        self.mock_llm.chat.return_value = ChatResponse(
            content='Invalid JSON content',
            model="test-model"
        )
        
        questions = await self.generator.generate("test query", "test answer")
        self.assertEqual(len(questions), 0)

    async def test_limit_to_three(self):
        # Mock more than 3 questions
        self.mock_llm.chat.return_value = ChatResponse(
            content='["1", "2", "3", "4", "5"]',
            model="test-model"
        )
        
        questions = await self.generator.generate("test", "test")
        self.assertEqual(len(questions), 3)

if __name__ == "__main__":
    unittest.main()
