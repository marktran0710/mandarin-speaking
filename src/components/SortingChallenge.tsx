import { useEffect, useState } from "react";
import { BiLabel, BiText } from "./BiLabel";
import type { Topic } from "./StoryRecorder";

interface SortingChallengeProps {
  topic: Topic;
  /** Whether the vocabulary quiz is still gating "practice" — determines
   * whether finishing/skipping the sort sends the student to "vocabquiz" or
   * straight to "practice". */
  speakingLocked: boolean;
  onContinue: (phase: "vocabquiz" | "practice") => void;
}

function shuffleImages(images: string[]) {
  if (!images || images.length === 0) return [];
  const scrambled = [...images];
  // Fisher-Yates shuffle
  for (let i = scrambled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [scrambled[i], scrambled[j]] = [scrambled[j], scrambled[i]];
  }
  // Swap first two if order is unchanged
  const isSameOrder = scrambled.every((img, idx) => img === images[idx]);
  if (isSameOrder && scrambled.length > 1) {
    const temp = scrambled[0];
    scrambled[0] = scrambled[1];
    scrambled[1] = temp;
  }
  return scrambled;
}

export default function SortingChallenge({
  topic,
  speakingLocked,
  onContinue,
}: SortingChallengeProps) {
  const [shuffledPool, setShuffledPool] = useState<string[]>([]);
  const [placedImages, setPlacedImages] = useState<Array<string | null>>([]);
  const [selectedPoolImage, setSelectedPoolImage] = useState<string | null>(
    null,
  );
  const [validationStates, setValidationStates] = useState<
    Array<"correct" | "incorrect" | null>
  >([]);
  const [sortingFeedback, setSortingFeedback] = useState<string>("");
  const [, setSortingAttempts] = useState(0);

  // Re-shuffle and reset whenever the topic changes (including on mount).
  useEffect(() => {
    setSelectedPoolImage(null);
    setSortingFeedback("");
    setSortingAttempts(0);
    setValidationStates(new Array(topic.images.length).fill(null));
    setShuffledPool(shuffleImages(topic.images));
    setPlacedImages(new Array(topic.images.length).fill(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic.id, topic.images]);

  const handleDragStart = (
    e: React.DragEvent,
    image: string,
    source: "pool" | "slot",
    index?: number,
  ) => {
    e.dataTransfer.setData(
      "text/plain",
      JSON.stringify({ image, source, index }),
    );
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const placePoolImageInSlot = (image: string, targetIndex: number) => {
    setPlacedImages((prev) => {
      const next = [...prev];
      const existingImage = next[targetIndex];
      next[targetIndex] = image;

      setShuffledPool((pool) => {
        const nextPool = pool.filter((img) => img !== image);
        if (existingImage) {
          nextPool.push(existingImage);
        }
        return nextPool;
      });

      return next;
    });
    setSelectedPoolImage(null);
    setValidationStates(new Array(topic.images.length).fill(null));
    setSortingFeedback("");
  };

  const swapSlots = (sourceIndex: number, targetIndex: number) => {
    setPlacedImages((prev) => {
      const next = [...prev];
      const temp = next[targetIndex];
      next[targetIndex] = next[sourceIndex];
      next[sourceIndex] = temp;
      return next;
    });
    setValidationStates(new Array(topic.images.length).fill(null));
    setSortingFeedback("");
  };

  const removeImageFromSlot = (slotIndex: number) => {
    const image = placedImages[slotIndex];
    if (!image) return;

    setPlacedImages((prev) => {
      const next = [...prev];
      next[slotIndex] = null;
      return next;
    });

    setShuffledPool((pool) => [...pool, image]);
    setSelectedPoolImage(null);
    setValidationStates(new Array(topic.images.length).fill(null));
    setSortingFeedback("");
  };

  const handleDropToSlot = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    try {
      const dataStr = e.dataTransfer.getData("text/plain");
      if (!dataStr) return;
      const data = JSON.parse(dataStr);
      const { image, source, index: sourceIndex } = data;

      if (source === "pool") {
        placePoolImageInSlot(image, targetIndex);
      } else if (source === "slot" && sourceIndex !== undefined) {
        swapSlots(sourceIndex, targetIndex);
      }
    } catch (err) {
      console.error("Drop to slot failed", err);
    }
  };

  const handleDropToPool = (e: React.DragEvent) => {
    e.preventDefault();
    try {
      const dataStr = e.dataTransfer.getData("text/plain");
      if (!dataStr) return;
      const data = JSON.parse(dataStr);
      const { source, index: sourceIndex } = data;

      if (source === "slot" && sourceIndex !== undefined) {
        removeImageFromSlot(sourceIndex);
      }
    } catch (err) {
      console.error("Drop to pool failed", err);
    }
  };

  const checkSequence = () => {
    const isAnySlotEmpty = placedImages.some((img) => img === null);
    if (isAnySlotEmpty) {
      setSortingFeedback(
        "請先把所有圖片放進場景再檢查！Please place all pictures into the scenes before checking!",
      );
      return;
    }

    const nextValidationStates = placedImages.map((image, index) => {
      return image === topic.images[index] ? "correct" : "incorrect";
    });
    setValidationStates(nextValidationStates);

    const isAllCorrect = nextValidationStates.every(
      (state) => state === "correct",
    );
    setSortingAttempts((prev) => prev + 1);

    if (isAllCorrect) {
      setSortingFeedback(
        "完全正確！做得很好，你已經把場景排成正確順序了！Spot on! Excellent job. You have arranged the scenes in the correct order!",
      );
    } else {
      setSortingFeedback(
        "有些圖片順序不對。請檢查紅色標示的場景並再試一次！Some pictures are not in the correct sequence. Check the red highlighted scenes and try again!",
      );
    }
  };

  const resetSorting = () => {
    setPlacedImages(new Array(topic.images.length).fill(null));
    setShuffledPool([...topic.images]);
    setSelectedPoolImage(null);
    setValidationStates(new Array(topic.images.length).fill(null));
    setSortingFeedback("");
  };

  return (
    <section className="sorting-challenge-container">
      {/* ── Header ── */}
      <div className="sorting-header">
        <div className="sorting-header-copy">
          <p className="eyebrow">
            <BiLabel k="step_1_arrange_scenes" />
          </p>
          <h1>
            <BiLabel k="put_the_story_in_order" />
          </h1>
          <p className="subtitle">
            <BiText k="drag_each_picture_into_the_correct_scene" />
          </p>
        </div>
        <div className="sorting-progress">
          <div className="sorting-progress-label">
            <BiLabel
              zh={`已放 ${placedImages.filter(Boolean).length} / ${placedImages.length}`}
              pinyin={`Yǐ fàng ${placedImages.filter(Boolean).length} / ${placedImages.length}`}
              en={`${placedImages.filter(Boolean).length} / ${placedImages.length} placed`}
            />
          </div>
          <div className="sorting-progress-bar">
            <div
              className="sorting-progress-fill"
              style={{
                width: `${placedImages.length === 0 ? 0 : (placedImages.filter(Boolean).length / placedImages.length) * 100}%`,
              }}
            />
          </div>
        </div>
      </div>

      {sortingFeedback && (
        <div
          className={`sorting-feedback-banner ${sortingFeedback.includes("Spot on") ? "success" : "info"}`}
        >
          <span className="feedback-icon">
            {sortingFeedback.includes("Spot on") ? "🎉" : "💡"}
          </span>
          <p>{sortingFeedback}</p>
        </div>
      )}

      {/* ── Scene slots ── */}
      <div className="sorting-slots-grid">
        {placedImages.map((image, index) => {
          const validation = validationStates[index];
          const scenePrompt = topic.prompts?.[index];
          const activateSlot = () => {
            if (selectedPoolImage)
              placePoolImageInSlot(selectedPoolImage, index);
            else if (image) removeImageFromSlot(index);
          };
          return (
            <div
              key={`slot-${index}`}
              className={`sorting-slot-card ${validation || ""} ${selectedPoolImage ? "droppable" : ""}`}
              role="button"
              tabIndex={0}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDropToSlot(e, index)}
              onClick={activateSlot}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  activateSlot();
                }
              }}
            >
              <div className="slot-header">
                <span className="slot-number">
                  <span className="slot-num-badge">{index + 1}</span>
                  <BiLabel
                    zh={`場景 ${index + 1}`}
                    pinyin={`Chǎngjǐng ${index + 1}`}
                    en={`Scene ${index + 1}`}
                  />
                </span>
                {validation === "correct" && (
                  <span className="slot-badge correct">✓</span>
                )}
                {validation === "incorrect" && (
                  <span className="slot-badge incorrect">✗</span>
                )}
              </div>

              <div className="slot-body">
                {image ? (
                  <div className="slot-image-wrapper">
                    <img
                      src={image}
                      alt={`Scene ${index + 1}`}
                      draggable
                      onDragStart={(e) =>
                        handleDragStart(e, image, "slot", index)
                      }
                    />
                    <button
                      type="button"
                      className="remove-slot-image"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeImageFromSlot(index);
                      }}
                      aria-label="Remove"
                    >
                      &times;
                    </button>
                  </div>
                ) : (
                  <div className="slot-placeholder">
                    <span className="placeholder-icon">🖼️</span>
                    <span className="placeholder-text">
                      {selectedPoolImage ? (
                        <BiLabel k="click_to_place" />
                      ) : (
                        <BiLabel k="drag_here" />
                      )}
                    </span>
                  </div>
                )}
              </div>

              {scenePrompt && (
                <div className="slot-footer">
                  <p className="slot-prompt">{scenePrompt}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Picture pool ── */}
      <div className="sorting-pool-section">
        <div className="sorting-pool-header">
          <h2>
            📷 <BiLabel k="picture_bank" />
          </h2>
          <p className="pool-helper-text">
            {selectedPoolImage ? (
              <BiText k="click_a_scene_slot_above_to_place_this_p" />
            ) : shuffledPool.length === 0 ? (
              <BiText k="all_pictures_placed_verify_below" />
            ) : (
              <BiText k="drag_a_picture_to_a_slot_or_click_to_sel" />
            )}
          </p>
        </div>
        <div
          className="sorting-pool"
          onDragOver={handleDragOver}
          onDrop={handleDropToPool}
        >
          {shuffledPool.length === 0 ? (
            <div className="pool-empty-state">
              <span className="star-icon">✨</span>
              <p>
                <BiLabel k="all_pictures_placed" />
              </p>
            </div>
          ) : (
            shuffledPool.map((image, poolIdx) => (
              <div
                key={poolIdx}
                className={`sorting-pool-card ${selectedPoolImage === image ? "selected" : ""}`}
                draggable
                role="button"
                tabIndex={0}
                onDragStart={(e) => handleDragStart(e, image, "pool")}
                onClick={() =>
                  setSelectedPoolImage(
                    selectedPoolImage === image ? null : image,
                  )
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelectedPoolImage(
                      selectedPoolImage === image ? null : image,
                    );
                  }
                }}
              >
                <img src={image} alt="Story picture" />
                <span className="drag-handle">
                  {selectedPoolImage === image ? (
                    <BiLabel k="selected" />
                  ) : (
                    <BiLabel k="drag_click" />
                  )}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Actions ── */}
      <div className="sorting-actions">
        <button
          type="button"
          className="btn-reset-sorting"
          onClick={resetSorting}
        >
          ↺ <BiLabel k="reset" />
        </button>

        {validationStates.some((s) => s === "correct") &&
        !validationStates.includes("incorrect") &&
        placedImages.every(Boolean) ? (
          <button
            type="button"
            className="btn-start-speaking"
            onClick={() => onContinue(speakingLocked ? "vocabquiz" : "practice")}
          >
            <BiLabel k="continue_to_speaking" />
          </button>
        ) : (
          <button
            type="button"
            className="btn-verify-sorting"
            onClick={checkSequence}
            disabled={placedImages.some((img) => img === null)}
          >
            <BiLabel k="verify_sequence" />
          </button>
        )}

        <button
          type="button"
          className="btn-skip-sorting"
          onClick={() => onContinue(speakingLocked ? "vocabquiz" : "practice")}
        >
          <BiLabel k="skip" />
        </button>
      </div>
    </section>
  );
}
