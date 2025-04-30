'use client';

import Link from 'next/link';
import { MountainIcon, Moon, Sun } from 'lucide-react';
import { SearchForm } from './search-form';
import { Button } from './ui/button';
import { useTheme } from 'next-themes';
import RiskWiseLogo from './riskwise_logo4.png';
import Image from 'next/image';

export function SiteHeader() {
  const { setTheme, theme } = useTheme();

  const navLinks = [
    { href: '/chat', label: 'Chat' },
    { href: '/reports', label: 'Reports' },
    { href: '/thinking-logs', label: 'Thinking Logs' },
  ];

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background text-foreground">
      <div className="flex h-16 items-center justify-between mx-6">
        <Link href="/chat" className="flex items-center gap-2" prefetch={false}>
          <Image src={RiskWiseLogo} alt="RiskWise Logo" className="w-10" />
          <span className="font-semibold text-primary">RiskWise</span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm font-medium md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="text-muted-foreground hover:text-foreground transition-colors"
              prefetch={false}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-4">
          <SearchForm />
          <Button variant="ghost" size="icon" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
            <span className="sr-only">Toggle theme</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
