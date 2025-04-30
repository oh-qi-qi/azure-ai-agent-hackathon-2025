import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { message, session_id } = body;

    if (!message) {
      return NextResponse.json(
        {
          status: 'error',
          response: null,
          error: 'Message is required',
          session_id: null,
        },
        { status: 400 }
      );
    }

    const response = await fetch('http://localhost:8000/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message,
        session_id: session_id || undefined, // Only include session_id if it exists
      }),
    });

    const data = await response.json();

    return NextResponse.json({
      status: 'success',
      response: data.response || '',
      error: null,
      session_id: data.session_id || null,
    });
  } catch (error) {
    return NextResponse.json(
      {
        status: 'error',
        response: null,
        error: error instanceof Error ? error.message : 'An error occurred',
        session_id: null,
      },
      { status: 500 }
    );
  }
}
