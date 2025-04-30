import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const id = (await params).id;
    const apiUrl = `http://localhost:8000/api/sessions/${id}`;

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
