import { useCopilotAdditionalInstructions } from "@copilotkit/react-core";
import { useChatStore } from "@/stores/chat-store";

export function useCopilotSourceContext() {
  const selectedSources = useChatStore((s) => s.selectedSources);

  const names = selectedSources.map((s) => s.name).join(", ");

  useCopilotAdditionalInstructions(
    {
      instructions: `The user has selected these data sources: ${names}. Only query these sources.`,
      available: selectedSources.length > 0 ? "enabled" : "disabled",
    },
    [names],
  );
}
