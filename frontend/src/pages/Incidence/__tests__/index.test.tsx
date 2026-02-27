import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Incidence from '../index';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import * as apiClient from '../../../api/client';

// Mock the API client
vi.mock('../../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>('../../../api/client');
  return {
    ...actual,
    fetchIncidences: vi.fn().mockResolvedValue([]),
    bulkResolveIncidences: vi.fn().mockResolvedValue({ message: 'Resolved' }),
    bulkIgnoreIncidences: vi.fn().mockResolvedValue({ message: 'Ignored' }),
  };
});

describe('Incidence Page Filtering interactions', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Incidence />
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it('debounces the search query and sends it to the API', async () => {
    renderComponent();

    // The component initially renders and fetches once with empty params
    expect(apiClient.fetchIncidences).toHaveBeenCalledWith({});
    vi.mocked(apiClient.fetchIncidences).mockClear();

    const searchInput = screen.getByPlaceholderText('Search by title...');
    
    // Type a query
    fireEvent.change(searchInput, { target: { value: 'error' } });
    
    // It should not fetch immediately (debouncing)
    expect(apiClient.fetchIncidences).not.toHaveBeenCalled();

    // After debounce (300ms + some buffer), it should fetch with q='error'
    await waitFor(() => {
      expect(apiClient.fetchIncidences).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'error' })
      );
    }, { timeout: 1000 });
  });

  it('serializes advanced filter parameters correctly', async () => {
    renderComponent();
    vi.mocked(apiClient.fetchIncidences).mockClear();

    // Open filters
    const filterButton = screen.getByRole('button', { name: /Filters/i });
    fireEvent.click(filterButton);

    // Set fingerprint
    const fingerprintInput = screen.getByPlaceholderText('Exact hash match');
    fireEvent.change(fingerprintInput, { target: { value: 'abc123hash' } });

    // Set status
    const statusSelect = screen.getByRole('combobox');
    fireEvent.change(statusSelect, { target: { value: 'OPEN' } });

    // Set first_seen_from and to
    // They are datetime-local inputs
    const inputs = screen.getAllByRole('textbox').concat(
      // querySelectorAll because datetime-local doesn't map cleanly to role sometimes
      Array.from(document.querySelectorAll('input[type="datetime-local"]'))
    ) as HTMLInputElement[];
    
    // The first datetime-local is first_seen_from
    const firstSeenFrom = inputs.find(i => i.type === 'datetime-local' && i.value === '')!;
    fireEvent.change(firstSeenFrom, { target: { value: '2023-10-01T12:00' } });

    // Assuming we don't trigger refetch automatically on change, we might need a button if "apply" existed
    // But index.tsx says we trigger change immediately via React Query when activeParams changes!
    // Wait, the hook `useQuery` has `activeParams` as queryKey. So any change updates it.
    
    await waitFor(() => {
      expect(apiClient.fetchIncidences).toHaveBeenCalledWith(
        expect.objectContaining({
          fingerprint: 'abc123hash',
          status: 'OPEN',
          // ISOString checks
          first_seen_from: new Date('2023-10-01T12:00').toISOString(),
        })
      );
    }, { timeout: 1000 });
  });
});

