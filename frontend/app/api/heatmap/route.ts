import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  try {
    // Get the URL parameters
    const { searchParams } = new URL(request.url);
    const conversation_id = searchParams.get('conversation_id');
    const session_id = searchParams.get('session_id');

    // Validate required parameters
    if (!conversation_id || !session_id) {
      return NextResponse.json({ error: 'Missing required parameters' }, { status: 400 });
    }

    // Forward the request to the backend
    const response = await fetch(
      `http://localhost:8000/api/heatmap?conversation_id=${conversation_id}&session_id=${session_id}`
    );

    if (!response.ok) {
      throw new Error(`Backend responded with status: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Heatmap API Error:', error);
    return NextResponse.json({ error: `Error retrieving heatmap data: ${error}` }, { status: 500 });
  }
}
