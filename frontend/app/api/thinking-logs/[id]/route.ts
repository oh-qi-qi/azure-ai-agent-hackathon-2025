import { NextRequest, NextResponse } from 'next/server';

interface Thought {
  thought_content: string;
  agent_name: string;
  thinking_stage: string;
}

interface Conversation {
  conversation_id: string;
  user_query: string;
  thoughts: Thought[];
}

interface ThinkingLogResponse {
  session_id: string;
  conversations: Conversation[];
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const id = (await params).id;
    const apiUrl = `http://localhost:8000/api/thinking-logs-by-session-id/${id}`;

    const response = await fetch(apiUrl);
    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json({ error: data.detail || 'Failed to fetch thinking logs' }, { status: response.status });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching thinking logs:', error);
    return NextResponse.json({ error: 'Failed to fetch thinking logs' }, { status: 500 });
  }
}
