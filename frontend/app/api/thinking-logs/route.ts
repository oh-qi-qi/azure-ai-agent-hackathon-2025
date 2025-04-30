import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const response = await fetch('http://localhost:8000/api/thinking-log-ids');
    const data = await response.json();

    return NextResponse.json({
      status: 'success',
      sessions: data,
      error: null,
    });
  } catch (error) {
    return NextResponse.json(
      {
        status: 'error',
        sessions: null,
        error: error instanceof Error ? error.message : 'An error occurred',
      },
      { status: 500 }
    );
  }
}
