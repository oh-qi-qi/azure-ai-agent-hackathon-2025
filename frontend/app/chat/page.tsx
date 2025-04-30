'use client';

import { ChatBubble, ChatBubbleAction, ChatBubbleAvatar, ChatBubbleMessage } from '@/components/ui/chat/chat-bubble';
import { ChatInput } from '@/components/ui/chat/chat-input';
import { ChatMessageList } from '@/components/ui/chat/chat-message-list';
import { Button } from '@/components/ui/button';
import { CopyIcon, CornerDownLeft, RefreshCcw, Volume2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
// import styles from './markdown-styles.module.css';
import styles from './markdown-styles-1.module.css';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import CodeDisplayBlock from '@/components/code-display-block';
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar';
import { ChatSessionSidebar } from './chat-session-sidebar';
import MapChart from './MapChart';
import { Tooltip } from 'react-tooltip';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  convo_id?: string; // Make it optional since not all messages will have it
  action?: string;
}

interface HeatmapData {
  country: string;
  average_risk: string;
  breakdown: string;
}

const ChatAiIcons = [
  {
    icon: CopyIcon,
    label: 'Copy',
  },
  {
    icon: RefreshCcw,
    label: 'Refresh',
  },
  {
    icon: Volume2,
    label: 'Volume',
  },
];

export default function ChatPage() {
  const [content, setContent] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hello! I am your AI assistant for procurement risk analysis. How can I assist you today?',
    },
  ]);
  const [input, setInput] = useState('');
  const [heatmapDataMap, setHeatmapDataMap] = useState<Record<string, HeatmapData[]>>({});

  const messagesRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (isGenerating || !input) return;
      setIsGenerating(true);
      handleSubmit(e as unknown as React.FormEvent<HTMLFormElement>);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!input.trim() || isGenerating) return;

    // Add user message
    const userMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsGenerating(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: input.trim(),
          session_id: sessionId,
        }),
      });

      const data = await response.json();

      if (data.status === 'success') {
        // Store the session ID for future messages
        if (data.session_id) {
          setSessionId(data.session_id);
        }

        // Add bot response
        const botMessage = {
          id: data.session_id || Date.now().toString(),
          role: 'assistant',
          content: data.response,
        };
        setMessages((prev) => [...prev, botMessage]);
      } else {
        // Handle error
        const errorMessage = {
          id: Date.now().toString(),
          role: 'assistant',
          content: `Error: ${data.error || 'Something went wrong'}`,
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    } catch (error) {
      // Handle network error
      const errorMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: 'Sorry, there was an error connecting to the server.',
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleActionClick = async (action: string, messageIndex: number) => {
    console.log('Action clicked:', action, 'Message index:', messageIndex);
    if (action === 'Refresh') {
      setIsGenerating(true);
      try {
        // Reload logic would go here
      } catch (error) {
        console.error('Error reloading:', error);
      } finally {
        setIsGenerating(false);
      }
    }

    if (action === 'Copy') {
      const message = messages[messageIndex];
      if (message && message.role === 'assistant') {
        navigator.clipboard.writeText(message.content);
      }
    }
  };

  const loadSession = async (id: string) => {
    console.log('Loading session:', id);
    try {
      const response = await fetch(`/api/chat/${id}`);
      const data = await response.json();
      console.log('Session data:', data);

      // Transform the API response into chat messages
      const transformedMessages = data.conversations.flatMap((conv: any) =>
        conv.messages
          .map((msg: any, i: number) => {
            const messages = [];

            if (i === 0 && msg.user_query) {
              messages.push({
                id: Date.now().toString(),
                role: 'user',
                content: msg.user_query,
              });
            }

            if (msg.agent_output && !msg.agent_output.startsWith('```json\n')) {
              if (msg.agent_name === 'Chatbot' || msg.action === 'Political Risk JSON Data') {
                messages.push({
                  id: Date.now().toString(),
                  role: 'assistant',
                  content: msg.agent_output,
                  convo_id: conv.conversation_id,
                  action: msg.action,
                });
              }
            }

            return messages;
          })
          .flat()
      );

      // Only update messages if we have some, otherwise keep the welcome message
      if (transformedMessages.length > 0) {
        setMessages(transformedMessages);
      }
      setSessionId(id);
      setIsGenerating(false); // Ensure generating state is reset
      setInput(''); // Clear any existing input

      // After transforming messages, check for Political Risk messages and fetch their heatmap data
      const politicalRiskMessages = transformedMessages.filter(
        (msg) => msg.action === 'Political Risk JSON Data' && msg.convo_id
      );

      // Fetch heatmap data for each relevant conversation
      for (const msg of politicalRiskMessages) {
        try {
          const response = await fetch(`/api/heatmap?conversation_id=${msg.convo_id}&session_id=${id}`);
          if (response.ok) {
            const data = await response.json();
            setHeatmapDataMap((prev) => ({
              ...prev,
              [msg.convo_id!]: data,
            }));
          }
        } catch (error) {
          console.error('Error fetching heatmap data:', error);
        }
      }
    } catch (error) {
      console.error('Error loading chat logs:', error);
    }
  };

  const handleHeatmapClick = async (convoId: string) => {
    try {
      console.log('Heatmap clicked:', convoId, sessionId);
      const response = await fetch(`/api/heatmap?conversation_id=${convoId}&session_id=${sessionId}`);
      if (!response.ok) {
        throw new Error(`Error: ${response.status}`);
      }
      const data = await response.json();
      console.log('Heatmap data:', data);
    } catch (error) {
      console.error('Error fetching heatmap data:', error);
    }
  };

  return (
    <SidebarProvider>
      <ChatSessionSidebar variant="inset" onSessionSelect={loadSession} />
      <SidebarInset>
        <main className="flex h-[90vh] px-2 pt-4 w-full flex-col items-center">
          <div className="flex items-center gap-2 px-4 pb-4 justify-start w-full">
            <SidebarTrigger />
            {!sessionId && <p className="text-lg font-bold">New Chat</p>}
            {sessionId && (
              <div className="flex items-center gap-2">
                <Badge variant="outline">
                  ID: {sessionId}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="ml-2 h-4 w-4 cursor-pointer hover:bg-blue-300 hover:text-blue-700"
                    onClick={() => navigator.clipboard.writeText(sessionId)}
                  >
                    <CopyIcon className="h-3 w-3" />
                  </Button>
                </Badge>
              </div>
            )}
          </div>

          <ScrollArea className="flex-1 w-full h-[60vh]">
            <ChatMessageList>
              {/* Messages */}
              {messages &&
                messages.map((message, index) => (
                  <ChatBubble key={index} variant={message.role == 'user' ? 'sent' : 'received'}>
                    <ChatBubbleAvatar src="" fallback={message.role == 'user' ? '👩🏻' : '🤖'} />
                    <ChatBubbleMessage>
                      {message.content.split('```').map((part: string, index: number) => {
                        if (index % 2 === 0) {
                          if (
                            message.action === 'Political Risk JSON Data' &&
                            message.convo_id &&
                            heatmapDataMap[message.convo_id]
                          ) {
                            return (
                              <div key={index}>
                                <MapChart setTooltipContent={setContent} breakdown={heatmapDataMap[message.convo_id]} />
                                <Tooltip id="country-tooltip" offset={10} place="top">
                                  {content}
                                </Tooltip>
                              </div>
                            );
                          } else {
                            return message.role === 'user' ? (
                              <p key={index}>{part}</p>
                            ) : (
                              <div key={index} className={`!text-default ${styles['markdown-body']}`}>
                                <Markdown remarkPlugins={[remarkGfm]}>{part}</Markdown>
                              </div>
                              // <div>{part.replace(/[\r\n]+/g, ' ')}</div>
                            );
                          }
                        } else {
                          return (
                            <pre className="whitespace-pre-wrap pt-2" key={index}>
                              <CodeDisplayBlock code={part} lang="" />
                            </pre>
                          );
                        }
                      })}

                      {message.role === 'assistant' && (
                        <div className="flex items-center mt-1.5 gap-1">
                          {!isGenerating && (
                            <>
                              {ChatAiIcons.map((icon, iconIndex) => {
                                const Icon = icon.icon;
                                return (
                                  <ChatBubbleAction
                                    variant="outline"
                                    className="size-5"
                                    key={iconIndex}
                                    icon={<Icon className="size-3" />}
                                    onClick={() => handleActionClick(icon.label, index)}
                                  />
                                );
                              })}
                              {/* Add Heatmap button if message has convo_id */}
                              {message.convo_id && message.action === 'Political Risk JSON Data' && (
                                <ChatBubbleAction
                                  variant="outline"
                                  className="size-5"
                                  icon={<span className="text-xs">🗺️</span>}
                                  onClick={() => handleHeatmapClick(message.convo_id)}
                                />
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </ChatBubbleMessage>
                  </ChatBubble>
                ))}

              {/* Loading */}
              {isGenerating && (
                <ChatBubble variant="received">
                  <ChatBubbleAvatar src="" fallback="🤖" />
                  <ChatBubbleMessage isLoading />
                </ChatBubble>
              )}
            </ChatMessageList>
          </ScrollArea>
          {/* Form and Footer fixed at the bottom */}
          <div className="w-full px-4 pb-4">
            <form
              ref={formRef}
              onSubmit={handleSubmit}
              className="relative rounded-lg border bg-background focus-within:ring-1 focus-within:ring-ring"
            >
              <ChatInput
                value={input}
                onKeyDown={onKeyDown}
                onChange={handleInputChange}
                placeholder="Type your message here..."
                className="rounded-lg bg-background border-0 shadow-none focus-visible:ring-0"
              />
              <div className="flex items-center p-3 pt-0 dark:bg-input/30">
                <Button disabled={!input || isGenerating} type="submit" size="sm" className="ml-auto gap-1.5">
                  Send Message
                  <CornerDownLeft className="size-3.5" />
                </Button>
              </div>
            </form>
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
