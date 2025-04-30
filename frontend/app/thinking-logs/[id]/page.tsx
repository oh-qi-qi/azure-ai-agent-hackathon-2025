'use client';

import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { useEffect, useRef, useState } from 'react';
import LeaderLine from 'leader-line-new';
import { motion, AnimatePresence } from 'framer-motion';
import { Badge } from '@/components/ui/badge';
import {
  Bot,
  BrainIcon,
  ChevronDown,
  Clock4Icon,
  ScrollTextIcon,
  SparkleIcon,
  User,
  UserCircle,
  Workflow,
} from 'lucide-react';
import { useParams } from 'next/navigation';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from '../../chat/markdown-styles.module.css';
import { VerticalTimeline, VerticalTimelineElement } from 'react-vertical-timeline-component';
import 'react-vertical-timeline-component/style.min.css';
import './vertical-timeline.css';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';

const isBrowser = typeof window !== 'undefined';

const MotionCard = motion(Card);

const getRandomColor = (seed: string) => {
  const colors = [
    'bg-teal-500 ',
    'bg-lime-500 ',
    'bg-fuchsia-500 ',
    'bg-cyan-500 ',
    'bg-green-500 ',
    'bg-rose-500 ',
    'bg-orange-500 ',
    'bg-pink-500 ',
    'bg-indigo-500 ',
    'bg-amber-500 ',
  ];
  // Create a simple hash of the seed string
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash = hash & hash; // Convert to 32-bit integer
  }
  // Use absolute value and modulo to get consistent positive index
  const index = Math.abs(hash) % colors.length;
  return colors[index];
};

// Add this component before the ThinkingLogPage component
const MotionChevron = motion(ChevronDown);

// Add this component before the ThinkingLogPage component
const CollapsibleSection = ({ thought }: { thought: any }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <Button variant="outline" size="sm" className="w-full flex items-center justify-between cursor-pointer">
          <span className="flex items-center gap-2">
            <ScrollTextIcon className="w-3 h-3" />
            Show Output
          </span>
          <MotionChevron className="h-4 w-4" animate={{ rotate: isOpen ? 180 : 0 }} transition={{ duration: 0.2 }} />
        </Button>
      </CollapsibleTrigger>
      <AnimatePresence initial={false}>
        {isOpen && (
          <CollapsibleContent forceMount>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className={`${styles['markdown-body']} bg-muted border !mt-4 rounded-lg p-4 !text-foreground text-default`}
            >
              <Markdown remarkPlugins={[remarkGfm]}>{thought.thinking_stage_output}</Markdown>
            </motion.div>
          </CollapsibleContent>
        )}
      </AnimatePresence>
    </Collapsible>
  );
};

export default function ThinkingLogPage() {
  const [thinkingData, setThinkingData] = useState<any>(null);
  const [mounted, setMounted] = useState(false);
  const params = useParams();
  const agentRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});
  const lineRefs = useRef<any[]>([]);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  useEffect(() => {
    const fetchThinkingLogs = async () => {
      if (params.id) {
        try {
          const response = await fetch(`/api/thinking-logs/${params.id}`);
          const data = await response.json();
          setThinkingData(data);
        } catch (error) {
          console.error('Error fetching thinking logs:', error);
        }
      }
    };

    fetchThinkingLogs();
  }, [params.id]);

  useEffect(() => {
    if (!isBrowser || !mounted || !thinkingData?.conversations?.length) return;

    const cleanup = () => {
      if (lineRefs.current) {
        lineRefs.current.forEach((line) => {
          try {
            if (line && typeof line.remove === 'function') {
              line.remove();
            }
          } catch (error) {
            console.error('Error removing line:', error);
          }
        });
        lineRefs.current = [];
      }
    };

    cleanup();

    const timer = setTimeout(() => {
      const conversations = thinkingData?.conversations;

      conversations.forEach((conversation: any) => {
        // Connect agents within each conversation
        for (let i = 0; i < conversation.agents.length - 1; i++) {
          const currentAgent = conversation.agents[i];
          const nextAgent = conversation.agents[i + 1];
          const currentRef = agentRefs.current[`${conversation.conversation_id}-${currentAgent.agent_name}`];
          const nextRef = agentRefs.current[`${conversation.conversation_id}-${nextAgent.agent_name}`];

          if (currentRef && nextRef) {
            try {
              const line = new LeaderLine(currentRef, nextRef, {
                color: 'rgb(156 163 175)',
                size: 3,
                path: 'fluid',
                startSocket: 'bottom',
                endSocket: 'top',
                startSocketGravity: 50,
                endSocketGravity: 50,
                startPlug: 'square',
                endPlug: 'arrow3',
                startPlugColor: '#1efdaa',
                endPlugColor: '#1a6be0',
                gradient: true,
                dash: {
                  animation: true,
                  len: 5,
                  gap: 3,
                },
              });

              lineRefs.current.push(line);

              if (typeof line.hide === 'function') {
                line.hide('none');
              }

              setTimeout(() => {
                if (typeof line.show === 'function') {
                  line.show('draw', {
                    duration: 1000,
                    timing: 'linear',
                  });
                }
              }, i * 200);
            } catch (error) {
              console.error('Error creating leader line:', error);
            }
          }
        }
      });
    }, 1000);

    return () => {
      clearTimeout(timer);
      cleanup();
    };
  }, [thinkingData, mounted]);

  return (
    <div className="w-full px-8 my-4">
      <MotionCard
        className="w-full border-none shadow-none bg-background"
        initial={{ opacity: 0, y: 0 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      >
        <div>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2, duration: 0.5 }}>
            <CardTitle>Thinking Process</CardTitle>
            <CardDescription>Multi-agent</CardDescription>
          </motion.div>
        </div>
        <div>
          <div className="flex flex-col">
            {thinkingData?.conversations.map((conversation: any, index: number) => (
              <motion.div
                key={conversation.conversation_id}
                className="w-full mb-8"
                initial={{ opacity: 0, x: 0 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{
                  delay: 0.3 + index * 0.1,
                  duration: 0.5,
                  ease: 'easeOut',
                }}
              >
                <div className="w-full border bg-muted p-4 rounded-xl">
                  <h3 className="flex items-center gap-2 font-semibold text-sm mb-4">
                    <User className="w-5 h-5" />
                    Query: {conversation.user_query}
                  </h3>

                  <div className="flex flex-col gap-3">
                    {conversation.agents.map((agent: any, agentIndex: number) => (
                      <motion.div
                        key={`${conversation.conversation_id}-${agent.agent_name}`}
                        ref={(el) => (agentRefs.current[`${conversation.conversation_id}-${agent.agent_name}`] = el)}
                        className={`bg-card text-card-foreground rounded-xl shadow-sm w-[60%] mb-20 ${
                          agentIndex % 2 === 0 ? 'self-start' : 'self-end'
                        }`}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{
                          delay: 0.5 + agentIndex * 0.1,
                          duration: 0.3,
                        }}
                      >
                        <div className="flex items-center justify-between mb-2 mt-4 mx-4">
                          <span className="flex items-center gap-2 text-sm text-blue-500 font-bold">
                            <Bot className="w-5 h-5" />
                            {agent.agent_name}
                          </span>
                        </div>
                        <VerticalTimeline lineColor="#ded4ff" layout="1-column-left">
                          {agent.thoughts.map((thought: any, thoughtIndex: number) => (
                            <VerticalTimelineElement
                              key={thoughtIndex}
                              icon={<BrainIcon className="w-2 h-2 p-1 text-default" />}
                            >
                              <div className="flex justify-between items-center">
                                <Badge className={`${getRandomColor(thought.thinking_stage)}`}>
                                  <Workflow className="w-3 h-3 mr-1" />
                                  {thought.thinking_stage}
                                </Badge>
                                <p className="text-muted-foreground font-medium">{thought.created_date}</p>
                              </div>

                              <div className="mb-4">
                                <p className="text-default">{thought.thought_content}</p>
                              </div>

                              <CollapsibleSection thought={thought} />
                            </VerticalTimelineElement>
                          ))}
                        </VerticalTimeline>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </MotionCard>
    </div>
  );
}
