from app.conversation.schemas import Scenario
from app.errors import TutorError

SCENARIOS = tuple(Scenario(**dict(zip(
    ('key', 'title', 'description', 'learner_role', 'tutor_role', 'goal', 'opening_line', 'minimum_level'), row))) for row in (
    ('introduction', 'First introductions', 'Meet someone for the first time.', 'new acquaintance', 'friendly new acquaintance', 'Introduce yourself and ask one question.', 'はじめまして。お名前は何ですか？', 'beginner'),
    ('restaurant', 'At a restaurant', 'Ask for a table, order and request the bill.', 'customer', 'restaurant server', 'Order food and a drink, then ask for the bill.', 'いらっしゃいませ。何名様ですか？', 'N5'),
    ('store', 'Convenience store', 'Buy an everyday item and answer the cashier.', 'customer', 'cashier', 'Ask for an item and respond about a bag.', 'いらっしゃいませ。何をお探しですか？', 'N5'),
    ('directions', 'Finding your way', 'Ask a local how to reach a destination.', 'traveler', 'helpful local resident', 'Ask for directions and confirm what you heard.', 'こんにちは。どこに行きたいですか？', 'N5'),
    ('station', 'At the train station', 'Ask about a train and buy a ticket.', 'traveler', 'station attendant', 'Explain your destination and ask about departure time.', 'こんにちは。どちらまでですか？', 'N5'),
    ('hotel', 'Hotel check-in', 'Introduce yourself at the reception desk.', 'guest', 'hotel receptionist', 'Check in and ask a question about your stay.', 'いらっしゃいませ。ご予約のお名前をお願いします。', 'N5'),
    ('coworker', 'Ask a coworker', 'Politely ask for help with a work task.', 'new employee', 'helpful coworker', 'Explain what you need and thank your coworker.', 'おはようございます。仕事はどうですか？', 'N4'),
    ('appointment', 'Make an appointment', 'Arrange a suitable time for a visit.', 'customer', 'receptionist', 'Request an appointment and confirm the day and time.', 'お電話ありがとうございます。ご予約ですか？', 'N4'),
))


def scenario(key):
    result = next((item for item in SCENARIOS if item.key == key), None)
    if result is None:
        raise TutorError('unknown_scenario', 'Choose an available conversation scenario.', 422)
    return result
