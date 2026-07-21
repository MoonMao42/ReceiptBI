import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  AnalysisServiceSelector,
  getAnalysisServicePresentation,
} from "@/components/chat/AnalysisServiceSelector";
import type { ModelSummary } from "@/lib/types/api";

const services: ModelSummary[] = [
  {
    id: "service-a",
    name: "日常分析",
    provider: "custom",
    model_id: "internal-model-a",
    is_default: true,
    is_active: true,
    credential_state: "readable",
    health_status: "healthy",
  },
  {
    id: "service-b",
    name: "深度分析",
    provider: "openai",
    model_id: "internal-model-b",
    is_default: false,
    is_active: true,
    credential_state: "readable",
    health_status: "unknown",
  },
  {
    id: "service-c",
    name: "旧服务",
    provider: "custom",
    model_id: "internal-model-c",
    is_default: false,
    is_active: true,
    credential_state: "readable",
    health_status: "unhealthy",
    last_error_category: "auth",
  },
];

describe("AnalysisServiceSelector", () => {
  it("shows business service names and health without provider details", () => {
    const onSelect = vi.fn();
    render(
      <AnalysisServiceSelector
        models={services}
        selectedModelId="service-a"
        onSelect={onSelect}
        onManage={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId("analysis-service-selector"));

    expect(screen.getByRole("option", { name: /日常分析/ })).toHaveTextContent("可用");
    expect(screen.getByRole("option", { name: /深度分析/ })).toHaveTextContent("未检查");
    expect(screen.getByRole("option", { name: /旧服务/ })).toHaveTextContent("需要重新连接");
    expect(screen.getByRole("option", { name: /旧服务/ })).toBeDisabled();
    expect(screen.queryByText("custom")).not.toBeInTheDocument();
    expect(screen.queryByText("internal-model-a")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("option", { name: /深度分析/ }));
    expect(onSelect).toHaveBeenCalledWith("service-b");
  });

  it("locks the service after an investigation starts", () => {
    render(
      <AnalysisServiceSelector
        models={services}
        selectedModelId="service-a"
        onSelect={vi.fn()}
        onManage={vi.fn()}
        locked
      />
    );

    const trigger = screen.getByTestId("analysis-service-selector");
    expect(trigger).toHaveAccessibleName("本次调查使用分析服务：日常分析");
    fireEvent.click(trigger);
    expect(screen.queryByRole("listbox", { name: "分析服务" })).not.toBeInTheDocument();
  });

  it("does not confuse a stored credential with a healthy service", () => {
    expect(
      getAnalysisServicePresentation({
        ...services[0],
        credential_state: "readable",
        health_status: "unhealthy",
        last_error_category: "connection",
      })
    ).toEqual({
      state: "temporarily_unavailable",
      label: "暂时不可用",
      selectable: false,
    });
  });
});
